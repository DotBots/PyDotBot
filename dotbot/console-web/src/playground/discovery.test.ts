import { describe, expect, it } from "vitest";

import { MemoryBus, topicMatches } from "./bus";
import {
  announceFilter,
  appNameFromTopic,
  appTopics,
  applyAnnouncement,
  parseAnnouncement,
} from "./discovery";
import type { AppAnnouncement } from "./types";

const FOLLOW = {
  name: "follow",
  title: "Follow the pointer",
  hint: "Move over the arena and the swarm follows.",
  inputs: ["pointer"],
  controls: [
    { id: "speed", type: "slider", min: 0, max: 100, value: 60, unit: "%" },
    { id: "wander", type: "toggle", value: true, label: "Wander when idle" },
  ],
  overlay: true,
  positions: false,
  protected: false,
  ui: null,
};

describe("topics", () => {
  it("builds the three topics of one app under one base", () => {
    expect(appTopics("2F00", "follow")).toEqual({
      announce: "dotbot/2F00/apps/follow",
      in: "dotbot/2F00/apps/follow/in",
      out: "dotbot/2F00/apps/follow/out",
    });
    expect(announceFilter("2F00")).toBe("dotbot/2F00/apps/+");
  });

  it("reads the app name off an announcement topic only", () => {
    expect(appNameFromTopic("dotbot/2F00/apps/follow", "2F00")).toBe("follow");
    expect(appNameFromTopic("dotbot/2F00/apps/follow/out", "2F00")).toBeNull();
    expect(appNameFromTopic("dotbot/0000/apps/follow", "2F00")).toBeNull();
    expect(appNameFromTopic("mari/2F00/apps/follow", "2F00")).toBeNull();
  });

  it("matches wildcards the way the broker does", () => {
    expect(topicMatches("dotbot/2F00/apps/+", "dotbot/2F00/apps/follow")).toBe(true);
    expect(topicMatches("dotbot/2F00/apps/+", "dotbot/2F00/apps/follow/in")).toBe(false);
    expect(topicMatches("dotbot/#", "dotbot/2F00/apps/follow/in")).toBe(true);
    expect(topicMatches("dotbot/2F00/apps/follow", "dotbot/2F00/apps/follow")).toBe(true);
  });
});

describe("parseAnnouncement", () => {
  it("takes a well-formed announcement whole", () => {
    const parsed = parseAnnouncement(FOLLOW);
    expect(parsed?.name).toBe("follow");
    expect(parsed?.inputs).toEqual(["pointer"]);
    expect(parsed?.controls.map((c) => c.id)).toEqual(["speed", "wander"]);
    expect(parsed?.overlay).toBe(true);
  });

  it("fills in what a terse script left out", () => {
    const parsed = parseAnnouncement({ name: "bare" });
    expect(parsed).toEqual({
      name: "bare",
      title: "bare",
      hint: "",
      inputs: [],
      controls: [],
      overlay: false,
      positions: false,
      protected: false,
      ui: null,
    });
  });

  it("drops input kinds and control types the page cannot render", () => {
    const parsed = parseAnnouncement({
      ...FOLLOW,
      inputs: ["pointer", "telepathy"],
      controls: [...FOLLOW.controls, { id: "x", type: "hologram" }, { type: "slider" }],
    });
    expect(parsed?.inputs).toEqual(["pointer"]);
    expect(parsed?.controls.map((c) => c.id)).toEqual(["speed", "wander"]);
  });

  it("refuses a payload that is not an announcement", () => {
    expect(parseAnnouncement(null)).toBeNull();
    expect(parseAnnouncement("follow")).toBeNull();
    expect(parseAnnouncement([FOLLOW])).toBeNull();
    expect(parseAnnouncement({ title: "no name" })).toBeNull();
  });
});

describe("applyAnnouncement", () => {
  it("adds an app the first time its announcement arrives", () => {
    const apps = applyAnnouncement([], "follow", FOLLOW);
    expect(apps.map((a) => a.name)).toEqual(["follow"]);
  });

  it("replaces an app in place when it republishes", () => {
    const first = applyAnnouncement([], "follow", FOLLOW);
    const second = applyAnnouncement(first, "follow", { ...FOLLOW, title: "Follow, tuned" });
    expect(second).toHaveLength(1);
    expect(second[0].title).toBe("Follow, tuned");
  });

  it("removes an app when the retained message is emptied", () => {
    const running = applyAnnouncement([], "follow", FOLLOW);
    expect(applyAnnouncement(running, "follow", null)).toEqual([]);
    expect(applyAnnouncement(running, "follow", "")).toEqual([]);
  });

  it("keeps a running app when a malformed payload arrives", () => {
    const running = applyAnnouncement([], "follow", FOLLOW);
    expect(applyAnnouncement(running, "follow", { title: "junk" })).toEqual(running);
    expect(applyAnnouncement(running, "follow", { name: "other" })).toEqual(running);
  });
});

describe("the rail over a bus", () => {
  it("fills from retained announcements and empties on the will", () => {
    const bus = new MemoryBus();
    const swarm = "2F00";
    bus.publish(appTopics(swarm, "follow").announce, FOLLOW, { retain: true });

    // A page opened after the demo started still sees it.
    let running: AppAnnouncement[] = [];
    const off = bus.subscribe(announceFilter(swarm), (payload, topic) => {
      const name = appNameFromTopic(topic, swarm);
      if (name !== null) running = applyAnnouncement(running, name, payload);
    });
    expect(running.map((a) => a.name)).toEqual(["follow"]);

    bus.publish(appTopics(swarm, "charging").announce, { name: "charging" }, { retain: true });
    expect(running.map((a) => a.name)).toEqual(["follow", "charging"]);

    // The will: an empty retained message on the same topic.
    bus.publish(appTopics(swarm, "follow").announce, null, { retain: true });
    expect(running.map((a) => a.name)).toEqual(["charging"]);

    off();
    bus.publish(appTopics(swarm, "letters").announce, { name: "letters" }, { retain: true });
    expect(running.map((a) => a.name)).toEqual(["charging"]);
  });

  it("ignores an app announced for another swarm", () => {
    const bus = new MemoryBus();
    let running: AppAnnouncement[] = [];
    bus.subscribe(announceFilter("2F00"), (payload, topic) => {
      const name = appNameFromTopic(topic, "2F00");
      if (name !== null) running = applyAnnouncement(running, name, payload);
    });
    bus.publish("dotbot/0000/apps/follow", FOLLOW, { retain: true });
    expect(running).toEqual([]);
  });
});
