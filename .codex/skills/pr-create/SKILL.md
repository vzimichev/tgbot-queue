---
name: pr-create
description: Creates a pull request and writes its description. Use when the user asks to create a PR or to prepare and submit a PR from the current changes.
---

When creating a pull request:

1. Inspect the repository state before making changes:
   - Run `git status --short --branch`.
   - Run `git diff main...HEAD` to inspect committed branch changes.
   - Run `git diff --cached` and `git diff` to include staged and unstaged changes when the branch is not committed yet.
   - Check the relevant tests and project instructions.
2. Do not create a pull request from `main` or another protected default branch. If the current branch is unsuitable, create or switch to a focused branch before committing.
3. Validate the changes with the narrowest relevant tests and checks. Report missing dependencies, services, credentials, or fixtures instead of claiming success.
4. Prepare a concise title and description following this format:

## What
One sentence explaining what this PR does.

## Why
Brief context on why this change is needed

## Changes
- Bullet points of specific changes made
- Group related changes together
- Mention any files deleted or renamed

5. If the changes are not committed, create a commit using the repository's commit naming convention. Do not include unrelated user changes.
6. Push the focused branch to its remote. Do not force-push or rewrite existing history.
7. Create the pull request with `gh pr create`, using the prepared title and description. Set the base branch explicitly, normally `main`.
8. Return the PR URL, title, base and head branches, a short summary of validation, and any remaining limitations.

Safety and authorization:

- Creating a PR includes committing and pushing only when the user explicitly requested PR creation, as in `/pr-create`. Otherwise stop after preparing the description and ask before commit, push, or PR creation.
- Never commit secrets, environment files, databases, generated media, credentials, or unrelated changes.
- Never expose tokens, passwords, activation links, or private payloads in the PR title or description.
- If GitHub CLI is unavailable or unauthenticated, provide the prepared title and body and explain what prevented PR creation.
