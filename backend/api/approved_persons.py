"""
Approved-persons whitelist API.

Admin can enroll known people (students/teachers) by submitting face images.
An ArcFace embedding (512-dim) is extracted via InsightFace and stored in the
database, then loaded into the in-memory ApprovedPersonsGallery so they never
trigger intruder alerts — regardless of their clothing.
"""

from __future__ import annotations

import base64
import json

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.dependencies import require_admin, require_viewer
from backend.database.db import get_db
from backend.database.models import ApprovedPerson

router = APIRouter(prefix="/api/approved-persons", tags=["approved-persons"])

_EMBEDDING_MODEL = "arcface_buffalo_s"


# ── Pydantic schemas ───────────────────────────────────────────────────────────


class EnrollRequest(BaseModel):
    name: str
    image_b64: str  # base64-encoded JPEG/PNG — face must be clearly visible
    notes: str | None = None


class SingleEnrollItem(BaseModel):
    name: str
    image_b64: str
    notes: str | None = None


class BatchEnrollRequest(BaseModel):
    persons: list[SingleEnrollItem]


class UpdateRequest(BaseModel):
    name: str | None = None
    notes: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────


def _decode_image(image_b64: str) -> np.ndarray:
    """Decode a base64-encoded JPEG/PNG to a BGR numpy array."""
    try:
        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("imdecode returned None")
        return frame
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid base64 image — send a JPEG or PNG",
        )


def _extract_embedding(frame: np.ndarray, gallery) -> np.ndarray:
    """
    Run InsightFace on the full image (enrollment path — no bbox crop).
    Raises HTTPException if no face is detected.
    """
    embedding = gallery.get_face_embedding(frame, person_bbox=None)
    if embedding is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No face detected in the image. "
                "Make sure the face is clearly visible, well-lit, and at least ~80px wide."
            ),
        )
    return embedding


def _get_gallery(request: Request):
    gallery = getattr(request.app.state, "approved_gallery", None)
    if gallery is None:
        raise HTTPException(status_code=503, detail="Face recognition gallery not initialised")
    return gallery


# ── Routes ─────────────────────────────────────────────────────────────────────


@router.get("")
def list_approved(
    _=Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """List all enrolled approved persons (metadata only, no embeddings)."""
    return [p.to_dict() for p in db.query(ApprovedPerson).order_by(ApprovedPerson.name).all()]


@router.post("/enroll", status_code=status.HTTP_201_CREATED)
def enroll_person(
    body: EnrollRequest,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Enroll a single person from a JPEG/PNG image (base64-encoded).

    The image must contain a clearly visible face.  An ArcFace embedding is
    extracted and stored; the person is immediately added to the in-memory
    gallery so they are recognised without a server restart.

    Typical use: camera capture from the live feed.
    """
    gallery = _get_gallery(request)
    frame = _decode_image(body.image_b64)
    embedding = _extract_embedding(frame, gallery)

    person = ApprovedPerson(
        name=body.name.strip(),
        descriptor=json.dumps(embedding.tolist()),
        notes=body.notes,
        enrolled_by=admin.id,
        embedding_model=_EMBEDDING_MODEL,
    )
    db.add(person)
    db.commit()
    db.refresh(person)

    gallery.add(person.id, embedding)
    return person.to_dict()


@router.post("/batch-enroll", status_code=status.HTTP_200_OK)
def batch_enroll(
    body: BatchEnrollRequest,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Enroll multiple persons in a single request.

    Each item in `persons` is processed independently.  The response is a list
    with one entry per submitted item:
      - status "ok"    → enrolled successfully; includes the created person dict
      - status "error" → failed; includes a `detail` field explaining why

    Partial success is allowed — if image 3 of 10 fails face detection, images
    1-2 and 4-10 are still enrolled.
    """
    gallery = _get_gallery(request)
    results: list[dict] = []

    for item in body.persons:
        try:
            frame = _decode_image(item.image_b64)
        except HTTPException as exc:
            results.append({"name": item.name, "status": "error", "detail": exc.detail})
            continue

        embedding = gallery.get_face_embedding(frame, person_bbox=None)
        if embedding is None:
            results.append({
                "name": item.name,
                "status": "error",
                "detail": "No face detected — ensure the face is clearly visible and well-lit",
            })
            continue

        try:
            person = ApprovedPerson(
                name=item.name.strip(),
                descriptor=json.dumps(embedding.tolist()),
                notes=item.notes,
                enrolled_by=admin.id,
                embedding_model=_EMBEDDING_MODEL,
            )
            db.add(person)
            db.commit()
            db.refresh(person)
            gallery.add(person.id, embedding)
            results.append({"status": "ok", **person.to_dict()})
        except Exception as exc:
            db.rollback()
            results.append({"name": item.name, "status": "error", "detail": str(exc)})

    return results


@router.patch("/{person_id}")
def update_person(
    person_id: int,
    body: UpdateRequest,
    _=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Rename a person or update their notes."""
    person = db.query(ApprovedPerson).filter(ApprovedPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    if body.name is not None:
        person.name = body.name.strip()
    if body.notes is not None:
        person.notes = body.notes
    db.commit()
    db.refresh(person)
    return person.to_dict()


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: int,
    request: Request,
    _=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a person from the approved whitelist."""
    person = db.query(ApprovedPerson).filter(ApprovedPerson.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    db.delete(person)
    db.commit()

    gallery = getattr(request.app.state, "approved_gallery", None)
    if gallery is not None:
        gallery.remove(person_id)
