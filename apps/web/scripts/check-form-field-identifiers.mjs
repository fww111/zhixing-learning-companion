import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const checks = [
  {
    file: "src/components/AuthPanel.tsx",
    snippets: [
      'id="register-username"',
      'name="username"',
      'id="register-email"',
      'name="email"',
      'id="login-account"',
      'name="account"',
      'id="auth-password"',
      'name="password"',
    ],
  },
  {
    file: "src/components/ProfileInterviewPanel.tsx",
    snippets: [
      'id="profile-answer"',
      'name="answer"',
      'id="profile-topic"',
      'name="topic"',
    ],
  },
];

const missing = [];

for (const check of checks) {
  const source = readFileSync(resolve(process.cwd(), check.file), "utf8");
  for (const snippet of check.snippets) {
    if (!source.includes(snippet)) {
      missing.push(`${check.file}: missing ${snippet}`);
    }
  }
}

if (missing.length > 0) {
  console.error(missing.join("\n"));
  process.exit(1);
}

console.log("form fields include stable id/name attributes");
