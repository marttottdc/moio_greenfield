import { describe, it, expect, vi } from "vitest";
import {
  fetchCrmWhatsappLogs,
  flattenCrmLogsToEvents,
  type WaMessageLog,
  type CrmWhatsappLogsResponse,
} from "./crmWhatsappLogsRepo";

vi.mock("@/lib/queryClient", () => ({ fetchJson: vi.fn() }));

/** Fixture matching GET /api/v1/crm/communications/whatsapp-logs/ response shape. */
const CRM_LOGS_FIXTURE: CrmWhatsappLogsResponse = {
  ok: true,
  message_count: 2,
  messages: [
    {
      msg_id: "wamid.abc123",
      recipient: "5491112345678",
      body: "Hi!",
      flow_execution_id: "exec-uuid-1",
      contact_phone: "5491112345678",
      contact_name: "John Doe",
      contact: { id: "contact-1", name: "John Doe", phone: "5491112345678", email: "" },
      created: "2026-02-08T12:00:00+00:00",
      updated: "2026-02-08T12:05:00+00:00",
      first_status: "sent",
      last_status: "read",
      latest_status: "read",
      statuses: [
        { status: "sent", occurred_at: "2026-02-08T12:00:01+00:00", timestamp: "2026-02-08T12:00:01Z" },
        { status: "delivered", occurred_at: "2026-02-08T12:01:00+00:00", timestamp: "2026-02-08T12:01:00Z" },
        { status: "read", occurred_at: "2026-02-08T12:05:00+00:00", timestamp: "2026-02-08T12:05:00Z" },
      ],
      events: [],
    },
    {
      msg_id: "wamid.def456",
      recipient: "5491198765432",
      body: "Hello",
      contact_phone: "5491198765432",
      contact_name: "Jane Smith",
      created: "2026-02-08T13:00:00+00:00",
      updated: "2026-02-08T13:00:05+00:00",
      first_status: "sent",
      last_status: "delivered",
      latest_status: "delivered",
      statuses: [
        { status: "sent", occurred_at: "2026-02-08T13:00:01+00:00" },
        { status: "delivered", occurred_at: "2026-02-08T13:00:05+00:00" },
      ],
    },
  ],
  pagination: { current_page: 1, total_pages: 1, total_items: 2 },
};

describe("crmWhatsappLogsRepo", () => {
  describe("flattenCrmLogsToEvents", () => {
    it("returns one event per status when statuses are present", () => {
      const messages = CRM_LOGS_FIXTURE.messages;
      const events = flattenCrmLogsToEvents(messages);

      // First message has 3 statuses → 3 events; second has 2 statuses → 2 events
      expect(events.length).toBe(5);

      const byMsgId = events.filter((e) => e.message_id === "wamid.abc123");
      expect(byMsgId.length).toBe(3);
      expect(byMsgId.map((e) => e.status)).toEqual(["sent", "delivered", "read"]);
      expect(byMsgId[0].contact_name).toBe("John Doe");
      expect(byMsgId[0].recipient).toBe("5491112345678");
      expect(byMsgId[0].message_id).toBe("wamid.abc123");
      expect(byMsgId[0].created_at).toBe("2026-02-08T12:00:01+00:00");
    });

    it("returns one event per message when statuses array is empty", () => {
      const messages: WaMessageLog[] = [
        {
          msg_id: "wamid.no-status",
          recipient: "5491100000000",
          body: "Test",
          latest_status: "sent",
          created: "2026-02-08T14:00:00+00:00",
          updated: "2026-02-08T14:00:01+00:00",
        },
      ];
      const events = flattenCrmLogsToEvents(messages);

      expect(events.length).toBe(1);
      expect(events[0].id).toBe("wamid.no-status");
      expect(events[0].message_id).toBe("wamid.no-status");
      expect(events[0].status).toBe("sent");
      expect(events[0].created_at).toBe("2026-02-08T14:00:01+00:00");
    });

    it("uses events when statuses is missing (legacy)", () => {
      const messages: WaMessageLog[] = [
        {
          msg_id: "wamid.legacy",
          recipient: "5491111111111",
          events: [
            { status: "sent", timestamp: "2026-02-08T15:00:00Z" },
            { status: "failed", timestamp: "2026-02-08T15:00:01Z", api_response: { error: "Invalid number" } },
          ],
        },
      ];
      const events = flattenCrmLogsToEvents(messages);

      expect(events.length).toBe(2);
      expect(events[0].status).toBe("sent");
      expect(events[1].status).toBe("failed");
      expect(events[1].error_message).toBe("Invalid number");
    });
  });

  describe("fetchCrmWhatsappLogs", () => {
    it("parses API response and returns messages with message_count and pagination", async () => {
      const { fetchJson } = await import("@/lib/queryClient");
      vi.mocked(fetchJson).mockResolvedValue(CRM_LOGS_FIXTURE);

      const result = await fetchCrmWhatsappLogs({ page: 1, page_size: 50 });

      expect(result.ok).toBe(true);
      expect(result.message_count).toBe(2);
      expect(result.messages).toHaveLength(2);
      expect(result.messages[0].msg_id).toBe("wamid.abc123");
      expect(result.messages[0].recipient).toBe("5491112345678");
      expect(result.messages[0].statuses).toHaveLength(3);
      expect(result.pagination).toEqual({ current_page: 1, total_pages: 1, total_items: 2 });
    });
  });
});
