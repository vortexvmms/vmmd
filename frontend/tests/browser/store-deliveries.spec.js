const { test, expect } = require("@playwright/test");

test("assigned driver uploads pickup proof, records delivery, and generates a WhatsApp update", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("vmms_session", JSON.stringify({
    access_token: "test", refresh_token: "test", expires_at: Date.now() + 3600000
  })));
  const id = "d5000000-0000-0000-0000-000000000001";
  const driver = "d1000000-0000-0000-0000-000000000004";
  const job = {
    id, reference: 42, asset_name: "Plate Compactor", asset_code: "EQ-018", from_name: "Site A",
    to_name: "Main Store", approved_quantity: 1, requested_quantity: 1, state: "assigned",
    needed_on: "2026-11-18", driver_id: driver, driver_name: "Test Driver", timeline: []
  };
  const changes = [];
  let proof;
  await page.route("**/api/v1/me", route => route.fulfill({ json: { role: "driver", user_id: driver } }));
  await page.route(/\/api\/v1\/store\/deliveries(?:[/?]|$)/, route => {
    const request = route.request();
    if (request.method() === "GET" && request.url().endsWith("/photo")) {
      return route.fulfill({ contentType: "image/jpeg", body: proof });
    }
    if (request.method() === "PUT") {
      expect(request.headers()["content-type"]).toBe("image/jpeg");
      job.photo_id = request.url().split("/").at(-1);
      return route.fulfill({ json: { id: job.photo_id } });
    }
    if (request.method() === "POST") {
      const { action, detail } = request.postDataJSON();
      changes.push(action);
      job.state = action === "pickup" ? "picked_up" : "delivered";
      job.timeline.push({action, detail, occurred_at: "2026-11-18T08:00Z", actor_name: "Test Driver"});
      if (action === "deliver") Object.assign(job, { delivered_at: "2026-11-18T08:00Z", recipient: detail.recipient });
      return route.fulfill({ json: { id } });
    }
    return route.fulfill({ json: { role: "driver", can_request: false, actor_id: driver, rows: [job], photos_enabled: true } });
  });
  await page.goto("/store-deliveries.html");
  await expect(page.getByRole("heading", { name: "My Deliveries" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Request equipment" })).toBeHidden();
  await page.getByRole("button", { name: /MOV-0042/ }).click();
  await expect(page.getByRole("button", { name: "Confirm pickup" })).toBeHidden();
  await page.getByRole("button", { name: "Take or upload pickup photo" }).click();
  const image = await page.evaluate(() => document.createElement("canvas").toDataURL("image/jpeg").split(",")[1]);
  proof = Buffer.from(image, "base64");
  await page.getByLabel("Photo of the equipment").setInputFiles({
    name: "equipment.jpg", mimeType: "image/jpeg", buffer: proof
  });
  await page.getByRole("button", { name: "Save photo" }).click();
  await expect(page.getByRole("img", { name: "Pickup photo of the equipment" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm pickup" }).click();
  await page.getByRole("button", { name: "Confirm pickup" }).click();
  await page.getByRole("button", { name: "Mark delivered" }).click();
  await page.getByLabel("Handed to").fill("Main Store storekeeper");
  await page.getByRole("button", { name: "Mark delivered" }).click();
  await page.getByRole("button", { name: "Generate WhatsApp update" }).click();
  await expect(page.getByLabel("WhatsApp update")).toHaveValue(/MOV-0042[\s\S]*Main Store storekeeper/);
  await expect(page.getByRole("link", { name: "Save photo" })).toBeVisible();
  expect(changes).toEqual(["pickup", "deliver"]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
