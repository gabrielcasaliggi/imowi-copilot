import assert from "node:assert/strict";
import { test } from "node:test";

import {
  consoleHref,
  decideHostRouting,
  hostsAreSplit,
  portalHref,
  type HostConfig,
} from "./public-hosts";

const split: HostConfig = {
  consoleHost: "ibot.ecolan.com",
  portalHost: "soporte.ecolan.com",
};

const local: HostConfig = { consoleHost: "", portalHost: "" };

test("hostsAreSplit solo con ambos distintos", () => {
  assert.equal(hostsAreSplit(split), true);
  assert.equal(hostsAreSplit(local), false);
  assert.equal(
    hostsAreSplit({ consoleHost: "ibot.ecolan.com", portalHost: "ibot.ecolan.com" }),
    false,
  );
});

test("sin split, links relativos (dev)", () => {
  assert.equal(portalHref("/", local), "/portal");
  assert.equal(portalHref("/privacidad", local), "/privacidad");
  assert.equal(consoleHref("/login", local), "/login");
});

test("con split, links absolutos por audiencia", () => {
  assert.equal(portalHref("/", split), "https://soporte.ecolan.com/");
  assert.equal(portalHref("/portal", split), "https://soporte.ecolan.com/");
  assert.equal(portalHref("/privacidad", split), "https://soporte.ecolan.com/privacidad");
  assert.equal(consoleHref("/login", split), "https://ibot.ecolan.com/login");
});

test("portal host: / reescribe a /portal", () => {
  assert.deepEqual(decideHostRouting("soporte.ecolan.com", "/", split), {
    type: "rewrite",
    pathname: "/portal",
  });
});

test("portal host: /portal canónico a /", () => {
  assert.deepEqual(decideHostRouting("soporte.ecolan.com", "/portal", split), {
    type: "redirect",
    url: "https://soporte.ecolan.com/",
  });
});

test("portal host: login y bandeja van a consola", () => {
  assert.deepEqual(decideHostRouting("soporte.ecolan.com", "/login", split), {
    type: "redirect",
    url: "https://ibot.ecolan.com/login",
  });
  assert.deepEqual(decideHostRouting("soporte.ecolan.com", "/inbox", split), {
    type: "redirect",
    url: "https://ibot.ecolan.com/inbox",
  });
  assert.deepEqual(decideHostRouting("soporte.ecolan.com", "/admin/roles", split), {
    type: "redirect",
    url: "https://ibot.ecolan.com/admin/roles",
  });
});

test("portal host: privacidad queda", () => {
  assert.deepEqual(decideHostRouting("soporte.ecolan.com", "/privacidad", split), {
    type: "next",
  });
});

test("console host: /portal y /privacidad van al público", () => {
  assert.deepEqual(decideHostRouting("ibot.ecolan.com", "/portal", split), {
    type: "redirect",
    url: "https://soporte.ecolan.com/",
  });
  assert.deepEqual(decideHostRouting("ibot.ecolan.com", "/privacidad", split), {
    type: "redirect",
    url: "https://soporte.ecolan.com/privacidad",
  });
});

test("console host: /login y estáticos no se tocan", () => {
  assert.deepEqual(decideHostRouting("ibot.ecolan.com", "/login", split), {
    type: "next",
  });
  assert.deepEqual(decideHostRouting("ibot.ecolan.com", "/_next/static/x.js", split), {
    type: "next",
  });
  assert.deepEqual(decideHostRouting("ibot.ecolan.com", "/eko-avatar.png", split), {
    type: "next",
  });
});

test("sin split no interviene", () => {
  assert.deepEqual(decideHostRouting("localhost", "/", local), { type: "next" });
  assert.deepEqual(decideHostRouting("localhost", "/portal", local), { type: "next" });
});

test("Host con puerto se normaliza", () => {
  assert.deepEqual(decideHostRouting("soporte.ecolan.com:443", "/", split), {
    type: "rewrite",
    pathname: "/portal",
  });
});
