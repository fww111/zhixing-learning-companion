import { describeError, pickSupportedMimeType } from "./useVoiceRecording.js";

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

type MediaRecorderGlobal = {
  isTypeSupported: (type: string) => boolean;
};

test("describeError maps microphone DOMExceptions to readable Chinese hints", () => {
  assert(
    describeError(new DOMException("blocked", "NotAllowedError")).includes("麦克风权限被拒绝"),
    "NotAllowedError should explain permission rejection"
  );
  assert(
    describeError(new DOMException("missing", "NotFoundError")).includes("未检测到麦克风"),
    "NotFoundError should explain missing device"
  );
  assert(
    describeError(new DOMException("busy", "NotReadableError")).includes("被其他应用占用"),
    "NotReadableError should explain device occupation"
  );
  assert(
    describeError(new DOMException("weird", "SecurityError")).includes("SecurityError"),
    "unknown DOMException should surface its name"
  );
});

test("describeError falls back safely for non-DOM errors", () => {
  assert(
    describeError(new Error("boom")) === "boom",
    "plain Error should keep its message"
  );
  assert(
    describeError("unexpected").includes("录音失败"),
    "non-Error value should use the generic failure hint"
  );
});

test("pickSupportedMimeType prefers webm opus when supported", () => {
  const original = (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
  const recorder: MediaRecorderGlobal = {
    isTypeSupported: () => true,
  };
  (globalThis as { MediaRecorder?: unknown }).MediaRecorder = recorder;
  try {
    assert(pickSupportedMimeType() === "audio/webm;codecs=opus", "should pick the highest-priority supported format");
  } finally {
    (globalThis as { MediaRecorder?: unknown }).MediaRecorder = original;
  }
});

test("pickSupportedMimeType returns empty string when nothing is supported", () => {
  const original = (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
  const recorder: MediaRecorderGlobal = {
    isTypeSupported: () => false,
  };
  (globalThis as { MediaRecorder?: unknown }).MediaRecorder = recorder;
  try {
    assert(pickSupportedMimeType() === "", "unsupported environments should fall back to MediaRecorder default");
  } finally {
    (globalThis as { MediaRecorder?: unknown }).MediaRecorder = original;
  }
});

test("pickSupportedMimeType returns empty string when MediaRecorder is absent", () => {
  const original = (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
  delete (globalThis as { MediaRecorder?: unknown }).MediaRecorder;
  try {
    assert(pickSupportedMimeType() === "", "missing MediaRecorder should not throw");
  } finally {
    (globalThis as { MediaRecorder?: unknown }).MediaRecorder = original;
  }
});
