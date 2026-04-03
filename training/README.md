# Training YOLO for monkey (or other custom animals)

The runtime app uses **COCO animal class ids** plus any ids you add in `EXTRA_ANIMAL_CLASS_IDS` (see `backend/config.py`). COCO does not include “monkey”, so you need **weights that include a monkey class**, then wire the class index into `.env`.

## Recommended approach (simple, fewer bugs)

Treat monkey like any other animal: incidents stay `detection_type: animal`, and the **label** shows `monkey` from the model.

1. **Build a dataset** in YOLO format (images + one `.txt` label file per image).  
   - Label tools: [LabelImg](https://github.com/tzutalin/labelImg), [Roboflow](https://roboflow.com), CVAT, etc.  
   - Classes: at minimum `person` and `monkey` (see `example_monkey_dataset.yaml`).

2. **Train** from the repo root:

   ```bash
   pip install -r requirements.txt
   python scripts/train_monkey_yolo.py --data training/datasets/monkey/data.yaml --epochs 50
   ```

   Adjust `--data` to your real YAML path. Training writes under `runs/detect/<name>/weights/best.pt`.

3. **Deploy weights**

   - Copy `best.pt` to e.g. `models/monkey_yolov8s.pt`.
   - In `.env`:

     ```env
     YOLO_MODEL_PATH=models/monkey_yolov8s.pt
     ```

   - For a **2-class** model (`person` = 0, `monkey` = 1), set:

     ```env
     EXTRA_ANIMAL_CLASS_IDS=1
     ```

     Leave `PERSON_CLASS_ID=0` (default).

4. **Restart the backend.** You should see incidents with label `monkey` and type Animal in the UI.

## Class indices (important)

- **2-class model** (`person`, `monkey`): `EXTRA_ANIMAL_CLASS_IDS=1`.  
- **COCO + extra classes** (advanced): if you append `monkey` as the last class after the 80 COCO classes, its index is often **80** (0–79 are COCO). Confirm with `model.names` in Python or Ultralytics logs, then set:

  ```env
  EXTRA_ANIMAL_CLASS_IDS=80
  ```

If your custom model uses a different index for `person`, set `PERSON_CLASS_ID` accordingly.

## Data tips

- Use varied lighting, distances, and backgrounds; include hard negatives (no animals).
- Start with **50–200+ labeled monkey images** for a usable prototype; more is better.
- Keep `val` split ~15–20% for metrics.

## What we do not ship in git

- Dataset images and trained `.pt` files are large; keep them local or in your own storage.  
- `models/*.pt` is gitignored; place weights locally and point `YOLO_MODEL_PATH` at them.
