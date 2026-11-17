// Autosave of one object's form, framework-free. One save at a time: a change typed while a save is in flight goes
// out right after it. The confirmed snapshot moves only on success, and only to what was sent, so edits typed
// meanwhile stay dirty; a failed save keeps its fields dirty and is retried by the next flush (next change / retry).

export type Patch = Record<string, unknown>;
export interface AutosaveState { saving: boolean; error: unknown }

export interface AutosaveOptions<F> {
  /** what changed from the confirmed form to the current one, in the request's shape ({} = nothing to save) */
  diff: (confirmed: F, current: F) => Patch;
  /** the request; keepalive = the page is going away (pagehide / hidden tab), the request should outlive it */
  send: (patch: Patch, keepalive: boolean) => Promise<unknown>;
  onSaved?: (result: unknown, patch: Patch) => void;
  onError?: (e: unknown) => void;
  onState?: (s: AutosaveState) => void;
}

export class Autosaver<F> {
  private base: F;
  private cur: F;
  private running: Promise<void> | null = null;
  private keepalive = false;
  error: unknown = null;

  constructor(initial: F, private o: AutosaveOptions<F>) { this.base = initial; this.cur = initial; }

  /** the last form the server confirmed */
  get confirmed(): F { return this.base; }
  get saving(): boolean { return !!this.running; }
  /** the form the user has now (call on every change, before flush) */
  update(cur: F) { this.cur = cur; }
  dirty(): boolean { return Object.keys(this.o.diff(this.base, this.cur)).length > 0; }

  /** Saves everything up to the current form; resolves when it is confirmed, rejects with the save's error.
   * While a save runs, a call joins it: the loop re-diffs after each answer and sends what was typed meanwhile. */
  flush(opts: { keepalive?: boolean } = {}): Promise<void> {
    if (opts.keepalive) this.keepalive = true;
    if (!this.running) {
      this.running = this.loop().finally(() => { this.running = null; this.keepalive = false; this.emit(); });
      this.emit();
    }
    return this.running;
  }

  private async loop() {
    for (;;) {
      const snap = this.cur;
      const patch = this.o.diff(this.base, snap);
      if (!Object.keys(patch).length) return;
      let r: unknown;
      try {
        r = await this.o.send(patch, this.keepalive);
      } catch (e) {
        this.error = e;
        this.o.onError?.(e);
        throw e;
      }
      this.base = snap;
      this.error = null;
      this.o.onSaved?.(r, patch);
    }
  }

  private emit() { this.o.onState?.({ saving: !!this.running, error: this.error }); }
}
