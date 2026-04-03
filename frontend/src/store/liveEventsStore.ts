import { create } from "zustand";

import type { LiveEvent } from "../hooks/useWebSocket";

export type FrameHandler = ((base64Jpeg: string) => void) | null;

interface LiveEventsState {
  events: LiveEvent[];
  connected: boolean;
  frameHandler: FrameHandler;
  setConnected: (v: boolean) => void;
  setFrameHandler: (handler: FrameHandler) => void;
  pushEvent: (event: LiveEvent, maxEvents: number) => void;
  clearEvents: () => void;
}

export const useLiveEventsStore = create<LiveEventsState>((set) => ({
  events: [],
  connected: false,
  frameHandler: null,

  setConnected: (v) => set({ connected: v }),
  setFrameHandler: (handler) => set({ frameHandler: handler }),

  pushEvent: (event, maxEvents) =>
    set((state) => ({
      // Newest first to match Dashboard's `events.slice(0, 8)`
      events: [event, ...state.events].slice(0, maxEvents),
    })),

  clearEvents: () => set({ events: [] }),
}));

