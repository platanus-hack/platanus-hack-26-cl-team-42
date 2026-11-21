import { expect, test } from "@playwright/test";

// Credentials of the user seeded by the backend dev entrypoint on startup.
const EMAIL = process.env.E2E_LOGIN_EMAIL ?? "test@localhost";
const PASSWORD = process.env.E2E_LOGIN_PASSWORD ?? "test";

test.describe("frontend smoke", () => {
  test("unauthenticated user lands on the login screen", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(
      page.getByRole("heading", { name: "Login", level: 1 }).or(
        page.getByRole("heading", { name: "Login" }),
      ),
    ).toBeVisible();
  });

  test("seeded dev user can log in with email and password", async ({
    page,
  }) => {
    await page.goto("/login");
    await page.getByPlaceholder("Email").fill(EMAIL);
    await page.getByPlaceholder("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Login" }).click();

    // Successful login redirects away from /login into the authenticated app,
    // whose sidebar displays the logged-in user's email.
    await expect(page).not.toHaveURL(/\/login$/);
    await expect(page.getByText(EMAIL)).toBeVisible();
  });
});
