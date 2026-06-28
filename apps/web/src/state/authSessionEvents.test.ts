import {
  AUTH_SESSION_EXPIRED_EVENT,
  notifyAuthSessionExpired,
  subscribeAuthSessionExpired
} from "./authSessionEvents.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

class FakeWindow {
  listeners = new Map<string, Set<() => void>>();

  addEventListener(type: string, handler: () => void) {
    const handlers = this.listeners.get(type) ?? new Set();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: () => void) {
    this.listeners.get(type)?.delete(handler);
  }

  dispatchEvent(event: Event) {
    this.listeners.get(event.type)?.forEach((handler) => handler());
    return true;
  }
}

test("broadcasts auth session expiration exactly once to active subscribers", () => {
  const originalWindow = globalThis.window;
  const fakeWindow = new FakeWindow() as unknown as Window & typeof globalThis;
  globalThis.window = fakeWindow;
  let count = 0;
  const unsubscribe = subscribeAuthSessionExpired(() => {
    count += 1;
  });

  notifyAuthSessionExpired();
  unsubscribe();
  notifyAuthSessionExpired();

  assert(AUTH_SESSION_EXPIRED_EVENT === "pla:auth-session-expired", "event name should stay stable");
  assert(count === 1, "active subscriber should be called once and unsubscribed handler should not run");
  globalThis.window = originalWindow;
});
