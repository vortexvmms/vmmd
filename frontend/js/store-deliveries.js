"use strict";

requireLogin();

const endpoint = "/api/v1/store/deliveries";
const el = id => document.getElementById(id);
const requestForm = el("request-form");
const jobForm = el("job-form");
const jobDialog = el("delivery-dialog");
const filter = el("delivery-filter");
const labels = {
  requested: "Requested", released: "Released", assigned: "Assigned", picked_up: "In transit",
  delivered: "Delivered · awaiting receipt", received: "Received", cancelled: "Cancelled",
  returned: "Returned to pickup location"
};
const actionLabels = {
  request: "Request submitted", release: "Confirm and release", assign: "Assign driver",
  photo: "Pickup photo uploaded", pickup: "Confirm pickup", deliver: "Mark delivered",
  receive: "Confirm receipt", issue: "Report issue", cancel: "Cancel request",
  return_to_source: "Confirm return to pickup"
};
const clock = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore"
});
const reference = row => "MOV-" + String(row.reference).padStart(4, "0");
const time = value => value ? clock.format(new Date(value)) : "";
const pending = new Map();
let register;
let rows = [];
let job;
let action;
let photoUrl;
let loadCount = 0;
let searchCount = 0;
let searchTimer;

function element(tag, text) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  return node;
}

function option(value, text, disabled = false) {
  const node = new Option(text, value);
  node.disabled = disabled;
  return node;
}

function button(text, handle, primary = false) {
  const node = element("button", text);
  node.type = "button";
  if (primary) node.className = "primary";
  node.addEventListener("click", handle);
  return node;
}

async function api(path = "", options = {}) {
  const response = await vmmsApi(endpoint + path, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "The delivery request could not be completed.");
  }
  return response;
}

async function getRegister(before) {
  const params = new URLSearchParams();
  if (before) params.set("before", before);
  if (filter.value) params.set("state", filter.value);
  return (await api("?" + params)).json();
}

async function load(append = false) {
  const current = ++loadCount;
  el("delivery-status").textContent = "Loading deliveries…";
  el("delivery-more").hidden = true;
  try {
    const result = await getRegister(append ? rows.at(-1)?.reference : null);
    if (current !== loadCount) return;
    register = result;
    const driver = result.role === "driver";
    el("delivery-title").textContent = driver ? "My Deliveries" : "Movement Register";
    el("delivery-new").hidden = !result.can_request;
    el("delivery-home").hidden = driver;
    el("delivery-logout").hidden = !driver;
    rows = append ? [...rows, ...result.rows] : result.rows;
    el("delivery-list").replaceChildren(...rows.map(row => {
      const item = button("", () => showJob(row));
      item.className = "delivery-row";
      item.append(
        element("strong", reference(row) + " · " + row.asset_name + " (" + row.asset_code + ")"),
        element("span", row.from_name + " → " + row.to_name),
        element("small", labels[row.state] + (row.driver_name ? " · " + row.driver_name : ""))
      );
      return item;
    }));
    el("delivery-more").hidden = !result.has_more;
    el("delivery-status").textContent = rows.length ? "" : "No movements match this view.";
  } catch (error) {
    if (current === loadCount) el("delivery-status").textContent = error.message;
  }
}

function command(id, name, values) {
  const key = JSON.stringify([id, name, values]);
  if (!pending.has(key)) pending.set(key, crypto.randomUUID());
  return api("/" + id, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({event: pending.get(key), action: name, detail: values})
  }).then(() => pending.delete(key));
}

function localDate() {
  const parts = new Intl.DateTimeFormat("en-SG", {
    day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Singapore"
  }).formatToParts(new Date());
  const part = kind => parts.find(item => item.type === kind).value;
  return [part("year"), part("month"), part("day")].join("-");
}

async function loadEquipment() {
  const count = ++searchCount;
  const fields = requestForm.elements;
  fields.asset_id.replaceChildren(option("", "Loading equipment…"));
  if (!fields.from_site.value) {
    fields.asset_id.replaceChildren(option("", "Choose a pickup location"));
    return;
  }
  const params = new URLSearchParams({search: fields.search.value});
  if (fields.from_site.value !== "main") params.set("source", fields.from_site.value);
  try {
    const items = await (await api("/equipment?" + params)).json();
    if (count !== searchCount) return;
    fields.asset_id.replaceChildren(option("", items.length ? "Select equipment" : "No matching equipment"),
      ...items.map(item => option(item.id, item.name + " · " + item.code + " · " + item.available + " available")));
  } catch (error) {
    if (count === searchCount) {
      fields.asset_id.replaceChildren(option("", "Unable to load equipment"));
      el("request-status").textContent = error.message;
    }
  }
}

let draft;
el("delivery-new").addEventListener("click", () => {
  requestForm.reset();
  draft = crypto.randomUUID();
  const fields = requestForm.elements;
  const locations = [{id: "main", name: "Main Store"}, ...register.locations];
  for (const name of ["from_site", "to_site"]) {
    fields[name].replaceChildren(option("", "Select location"), ...locations.map(l => option(l.id, l.name)));
  }
  fields.needed_on.value = localDate();
  el("request-status").textContent = "";
  loadEquipment();
  el("request-dialog").showModal();
});
requestForm.elements.from_site.addEventListener("change", loadEquipment);
requestForm.elements.search.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadEquipment, 230);
});
requestForm.addEventListener("submit", async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(requestForm));
  for (const field of ["from_site", "to_site"]) if (values[field] === "main") values[field] = null;
  delete values.search;
  const submit = requestForm.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    await command(draft, "request", values);
    el("request-dialog").close();
    filter.value = "";
    await load();
  } catch (error) {
    el("request-status").textContent = error.message;
  } finally { submit.disabled = false; }
});

function resetPhoto() {
  if (photoUrl) URL.revokeObjectURL(photoUrl);
  photoUrl = null;
  el("job-photo").hidden = true;
  el("job-photo").removeAttribute("src");
  for (const id of ["share-photo", "copy-photo", "save-photo"]) el(id).hidden = true;
}

function downloadName(row, mime) {
  const extension = {"image/png": "png", "image/webp": "webp", "image/jpeg": "jpg"}[mime] || "jpg";
  return reference(row) + "." + extension;
}

async function showPhoto(row) {
  try {
    const data = await (await api("/" + row.id + "/photo")).blob();
    if (job !== row || !jobDialog.open) return;
    photoUrl = URL.createObjectURL(data);
    el("job-photo").src = photoUrl;
    el("job-photo").hidden = false;
    const file = new File([data], downloadName(row, data.type), {type: data.type});
    el("save-photo").href = photoUrl;
    el("save-photo").download = file.name;
    el("save-photo").hidden = false;
    if (navigator.canShare?.({files: [file]})) {
      el("share-photo").hidden = false;
      el("share-photo").onclick = async () => {
        try { await navigator.share({files: [file]}); }
        catch (error) { if (error.name !== "AbortError") el("job-status").textContent = "Use Save photo and attach it in WhatsApp."; }
      };
    }
    if (navigator.clipboard?.write && typeof ClipboardItem === "function") {
      const png = await toPng(data).catch(() => null);
      if (!png || job !== row || !jobDialog.open) return;
      el("copy-photo").hidden = false;
      el("copy-photo").onclick = async () => {
        try {
          await navigator.clipboard.write([new ClipboardItem({"image/png": png})]);
          el("job-status").textContent = "Photo copied.";
        } catch (_) { el("job-status").textContent = "Use Share photo or Save photo to attach it."; }
      };
    }
  } catch (error) {
    if (job === row && jobDialog.open) el("job-status").textContent = error.message;
  }
}

async function toPng(blob) {
  if (blob.type === "image/png") return blob;
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = element("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    canvas.getContext("2d").drawImage(bitmap, 0, 0);
    return await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
  } finally { bitmap.close(); }
}

function summary(row) {
  const quantity = row.approved_quantity ?? row.requested_quantity;
  return [
    row.asset_name + " (" + row.asset_code + ") · " + quantity + " item(s)",
    row.from_name + " → " + row.to_name,
    labels[row.state] + (row.driver_name ? " · Driver " + row.driver_name : ""),
    "Required " + row.needed_on,
    ...(row.request_note ? [row.request_note] : [])
  ];
}

function whatsAppText(row) {
  return [
    "*VCMS Equipment Movement · " + reference(row) + "*",
    row.approved_quantity + " × " + row.asset_name + " (" + row.asset_code + ")",
    row.from_name + " → " + row.to_name, "Driver " + row.driver_name,
    ...(row.delivered_at ? ["Delivered " + time(row.delivered_at), "Handed to " + row.recipient] : ["Picked up · In transit"]),
    ...(row.state === "received" ? ["Receipt confirmed"] : [])
  ].join("\n");
}

function actionsFor(row) {
  const driver = register.role === "driver";
  const available = [];
  if (row.state === "requested" && row.can_release) available.push("release");
  if (["released", "assigned"].includes(row.state) && row.can_dispatch) available.push("assign");
  if (driver && row.state === "assigned") available.push(row.photo_id ? "pickup" : "upload");
  if (driver && row.state === "picked_up") available.push("deliver");
  if (row.state === "delivered" && row.can_receive) available.push("receive");
  if (!["received", "cancelled", "returned"].includes(row.state)) available.push("issue");
  if (!driver && ["requested", "released", "assigned"].includes(row.state) &&
      (row.can_dispatch || row.requested_by === register.actor_id)) available.push("cancel");
  if (["picked_up", "delivered"].includes(row.state) && row.can_return) available.push("return_to_source");
  return available;
}

function showJob(row) {
  job = row;
  action = null;
  resetPhoto();
  el("job-status").textContent = "";
  el("job-title").textContent = reference(row);
  el("job-summary").replaceChildren(...summary(row).map(line => element("p", line)));
  const timeline = row.timeline.map(event => {
    const detail = event.detail || {};
    const extras = [
      detail.quantity == null ? null : "Qty " + detail.quantity,
      detail.driver, detail.recipient, detail.note
    ].filter(Boolean);
    return element("li", [time(event.occurred_at), actionLabels[event.action] || event.action,
      event.actor_name, ...extras].join(" · "));
  });
  el("job-timeline").replaceChildren(...timeline);
  const actions = actionsFor(row).map((name, index) =>
    button(name === "upload" ? "Take or upload pickup photo" : actionLabels[name], () => openAction(name), index === 0));
  if (["picked_up", "delivered", "received"].includes(row.state) && row.photo_id) {
    actions.push(button("Generate WhatsApp update", () => {
      el("job-message").value = whatsAppText(row);
      el("job-whatsapp").hidden = false;
      el("job-message").focus();
    }));
  }
  el("job-actions").replaceChildren(...actions);
  el("job-actions").hidden = false;
  jobForm.hidden = true;
  el("job-whatsapp").hidden = true;
  el("job-photo-section").hidden = !row.photo_id;
  if (!jobDialog.open) jobDialog.showModal();
  if (row.photo_id) showPhoto(row);
}

function field(label, control, name, required = true) {
  const wrapper = element("label", label);
  control.name = name;
  control.required = required;
  wrapper.append(control);
  return wrapper;
}

function openAction(name) {
  action = name;
  el("job-status").textContent = "";
  const fields = el("job-fields");
  fields.replaceChildren();
  if (name === "release" || name === "receive") {
    const quantity = element("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.max = String(job.approved_quantity ?? job.requested_quantity);
    quantity.value = quantity.max;
    fields.append(field(name === "release" ? "Quantity to release" : "Quantity received", quantity, "quantity"));
  }
  if (name === "assign") {
    const select = element("select");
    select.append(option("", "Select driver"), ...register.drivers.map(d => option(d.id, d.name)));
    select.value = job.driver_id || "";
    fields.append(field("Driver", select, "driver_id"));
    if (!register.drivers.length) el("job-status").textContent = "Create an active Driver account in User Management.";
  }
  if (name === "deliver") {
    const recipient = element("input");
    recipient.maxLength = 100;
    fields.append(field("Handed to", recipient, "recipient"));
  }
  if (name === "upload") {
    const photo = element("input");
    photo.type = "file";
    photo.accept = "image/*";
    photo.setAttribute("capture", "environment");
    fields.append(field("Photo of the equipment", photo, "photo"));
    if (!register.photos_enabled) el("job-status").textContent = "Photo storage is temporarily unavailable.";
  } else {
    const note = element("textarea");
    note.maxLength = 500;
    const needsNote = ["issue", "cancel", "return_to_source"].includes(name);
    fields.append(field(needsNote ? "Reason" : "Notes (optional)", note, "note", needsNote));
  }
  el("job-actions").hidden = true;
  el("action-submit").textContent = name === "upload" ? "Save photo" : actionLabels[name];
  jobForm.hidden = false;
  fields.querySelector("input,select,textarea")?.focus();
}

const photoIds = new Map();
async function uploadPhoto(id, file) {
  const key = JSON.stringify([id, file.name, file.lastModified, file.size]);
  if (!photoIds.has(key)) photoIds.set(key, crypto.randomUUID());
  const blob = await preparePhoto(file);
  await api("/" + id + "/photo/" + photoIds.get(key), {
    method: "PUT", headers: {"Content-Type": blob.type}, body: blob
  });
  photoIds.delete(key);
}

jobForm.addEventListener("submit", async event => {
  event.preventDefault();
  const row = job;
  const values = Object.fromEntries(new FormData(jobForm));
  const submit = el("action-submit");
  submit.disabled = true;
  el("job-status").textContent = "Saving…";
  try {
    if (action === "upload") await uploadPhoto(row.id, values.photo);
    else await command(row.id, action, values);
    jobDialog.close();
    await load();
    const updated = rows.find(item => item.id === row.id);
    if (updated && !jobDialog.open) showJob(updated);
  } catch (error) {
    el("job-status").textContent = error.message;
  } finally { submit.disabled = false; }
});

el("copy-message").addEventListener("click", async () => {
  const message = el("job-message");
  try {
    await navigator.clipboard.writeText(message.value);
    el("job-status").textContent = "Message copied. Paste it into WhatsApp and attach the photo.";
  } catch (_) {
    message.focus();
    message.select();
    el("job-status").textContent = "Use your device’s Copy command.";
  }
});
el("action-back").addEventListener("click", () => showJob(job));
jobDialog.addEventListener("close", () => { if (!jobDialog.open) resetPhoto(); });
document.querySelectorAll("[data-close]").forEach(node => node.addEventListener("click", () => node.closest("dialog").close()));
for (const [value, label] of Object.entries(labels)) filter.append(option(value, label));
filter.addEventListener("change", () => load());
el("delivery-refresh").addEventListener("click", () => load());
el("delivery-more").addEventListener("click", () => load(true));
el("delivery-logout").addEventListener("click", vmmsLogout);
load();
