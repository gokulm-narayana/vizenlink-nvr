"""Unit tests for ONVIF PullPoint XML parsing and clock drift detection."""

from __future__ import annotations

from vizenlink_nvr.events.onvif_pullpoint import (
    parse_notification_messages,
    parse_pullpoint_response_address,
)
from vizenlink_nvr.services.events import ClockSyncState, EventType
from vizenlink_nvr.timeutil import utc_now

SAMPLE_SUBSCRIBE_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://www.w3.org/2005/08/addressing"
  xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
  <s:Body>
    <tev:CreatePullPointSubscriptionResponse>
      <tev:SubscriptionReference>
        <wsa:Address>http://192.168.1.100:80/onvif/subscription?idx=12345</wsa:Address>
      </tev:SubscriptionReference>
      <wsnt:CurrentTime xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">2026-11-04T12:00:00Z</wsnt:CurrentTime>
      <wsnt:TerminationTime xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">2026-11-04T12:01:00Z</wsnt:TerminationTime>
    </tev:CreatePullPointSubscriptionResponse>
  </s:Body>
</s:Envelope>
"""

SAMPLE_PULL_RESPONSE_SYNCED = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tev:PullMessagesResponse xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
      <wsnt:NotificationMessage>
        <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:RuleEngine/CellMotionDetector/Motion</wsnt:Topic>
        <wsnt:Message>
          <tt:Message UtcTime="2026-11-04T12:00:00Z" PropertyOperation="Changed">
            <tt:Source>
              <tt:SimpleItem Name="Rule" Value="MotionRule1"/>
            </tt:Source>
            <tt:Data>
              <tt:SimpleItem Name="IsInside" Value="true"/>
              <tt:SimpleItem Name="State" Value="true"/>
            </tt:Data>
          </tt:Message>
        </wsnt:Message>
      </wsnt:NotificationMessage>
      <wsnt:NotificationMessage>
        <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:RuleEngine/LineDetector/LineCrossed</wsnt:Topic>
        <wsnt:Message>
          <tt:Message UtcTime="2026-11-04T12:00:01Z" PropertyOperation="Changed">
            <tt:Data>
              <tt:SimpleItem Name="Direction" Value="RightToLeft"/>
            </tt:Data>
          </tt:Message>
        </wsnt:Message>
      </wsnt:NotificationMessage>
    </tev:PullMessagesResponse>
  </s:Body>
</s:Envelope>
"""

SAMPLE_PULL_RESPONSE_DRIFT = """<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:tt="http://www.onvif.org/ver10/schema">
  <s:Body>
    <tev:PullMessagesResponse xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
      <wsnt:NotificationMessage>
        <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:RuleEngine/TamperDetector/Tamper</wsnt:Topic>
        <wsnt:Message>
          <!-- Camera clock is 2 hours in the past -->
          <tt:Message UtcTime="2026-11-04T10:00:00Z" PropertyOperation="Changed">
            <tt:Data>
              <tt:SimpleItem Name="State" Value="true"/>
            </tt:Data>
          </tt:Message>
        </wsnt:Message>
      </wsnt:NotificationMessage>
    </tev:PullMessagesResponse>
  </s:Body>
</s:Envelope>
"""


def test_parse_pullpoint_address() -> None:
    """Verify subscription address is extracted from response XML."""
    addr = parse_pullpoint_response_address(SAMPLE_SUBSCRIBE_RESPONSE)
    assert addr == "http://192.168.1.100:80/onvif/subscription?idx=12345"


def test_parse_synced_notifications() -> None:
    """Verify parsing multiple notification messages when camera clock is in sync."""
    now = utc_now().replace(year=2026, month=11, day=4, hour=12, minute=0, second=0, microsecond=0)
    events = parse_notification_messages(SAMPLE_PULL_RESPONSE_SYNCED, "CAM-TEST-01", now)

    assert len(events) == 2

    # Event 1: Motion
    e1 = events[0]
    assert e1.camera_serial == "CAM-TEST-01"
    assert e1.event_type == EventType.MOTION
    assert e1.clock_sync_state == ClockSyncState.SYNCED
    assert e1.data.get("State") == "true"
    assert e1.data.get("IsInside") == "true"

    # Event 2: Line crossing
    e2 = events[1]
    assert e2.camera_serial == "CAM-TEST-01"
    assert e2.event_type == EventType.LINE_CROSSING
    assert e2.clock_sync_state == ClockSyncState.SYNCED
    assert e2.data.get("Direction") == "RightToLeft"


def test_clock_drift_compensation_restamps_time() -> None:
    """Verify that when clock deviates > 5s, state is uncertain and time is restamped."""
    now = utc_now().replace(year=2026, month=11, day=4, hour=12, minute=0, second=0, microsecond=0)
    events = parse_notification_messages(SAMPLE_PULL_RESPONSE_DRIFT, "CAM-TEST-01", now)

    assert len(events) == 1
    e = events[0]
    assert e.event_type == EventType.TAMPER
    assert e.clock_sync_state == ClockSyncState.UNCERTAIN
    assert e.clock_drift_seconds is not None
    assert e.clock_drift_seconds > 7000  # 2 hours offset
    # Re-stamped with NVR time
    assert e.utc_time == now
