import { AuthProvider } from "./auth.js";

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

const source = AuthProvider.toString();

test("keeps profile loading callbacks stable for route guard effects", () => {
  assert(
    source.includes("useCallback"),
    "auth provider must use React useCallback for functions consumed by route guard effects"
  );
  assert(
    source.includes("loadProfile") && source.indexOf("useCallback") < source.indexOf("loadProfile"),
    "loadProfile should be memoized so refreshProfile can stay stable"
  );
  assert(
    source.includes("refreshProfile") && source.indexOf("useCallback") < source.indexOf("refreshProfile"),
    "refreshProfile should be memoized to avoid repeatedly restarting RequireCourseProfile"
  );
});
