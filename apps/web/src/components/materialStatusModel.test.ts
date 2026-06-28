import { materialStatusesSettledAfterBackgroundWork } from "./materialStatusModel.js";

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

test("detects background material processing settling for chunk refresh", () => {
  assert(
    materialStatusesSettledAfterBackgroundWork(
      [{ id: 1, parse_status: "indexing" }],
      [{ id: 1, parse_status: "parsed" }]
    ),
    "indexing to parsed should refresh dependent chunks"
  );
  assert(
    materialStatusesSettledAfterBackgroundWork(
      [{ id: 2, parse_status: "mineru_polling" }],
      [{ id: 2, parse_status: "index_failed" }]
    ),
    "active to final failure should refresh dependent panels"
  );
  assert(
    !materialStatusesSettledAfterBackgroundWork(
      [{ id: 3, parse_status: "parsed" }],
      [{ id: 3, parse_status: "parsed" }]
    ),
    "unchanged final status should not repeatedly refresh"
  );
});
