# Smart Pump: Research Report and References

*Generated: 2026-10-03 | Sources: 24 consulted, 19 cited | Confidence: **High** on the technical stack (primary docs), **Medium** on the domain and market (a few primary sources plus search summaries), **Low** on standards (paywalled, not read)*

Companion to [`PRD.md`](PRD.md) and [`ARCHITECTURE-DIAGRAMS.md`](ARCHITECTURE-DIAGRAMS.md). Prototype, not a medical device; nothing here is clinical guidance.

> **How to read the excerpts.** Pages were fetched with an extraction tool that returns quoted passages. Treat the passages marked **Doc excerpt** as close to verbatim. Re-check the live page before you put a quote on a slide. Passages marked **Search summary** came from a search-engine digest and are **unverified**: the full text could not be fetched (paywall, cookie wall, or timeout). No source contained instructions aimed at an agent.

---

## Executive summary

1. **Domain.** The literature on home tube feeding points to gaps in training and information (only 8% of surveyed carers had read written guidance [R1]) and to weak follow-up after discharge [R2]. Search summaries also mention poor understanding of pump alarms and disturbed sleep at night [R1]. This supports our family-side focus on plain-language alerts and night use.
2. **Market.** The best-known connected enteral pump, Cardinal Health's Kangaroo Connect, offers feeding history, an attainment report, remote troubleshooting, and remote software updates [R3]. **We found no public evidence of remote prescription changes with caregiver confirmation**, which is our differentiator. This is a medium-confidence negative finding.
3. **Regulation.** Enteral pumps fall under FDA's infusion pump category, where software defects and user interface issues are the most common reported problems [R4]. IEC 60601-2-24 explicitly covers enteral nutrition pumps [R18]. FDA's cybersecurity guidance (2023, updated June 2025) would apply to a real connected version [R5].
4. **Technical stack.** Four documented library behaviours break assumptions in the current plan. PubSubClient publishes only at QoS 0 and has a 256-byte default buffer, which our prescription message overflows [R10]. Mosquitto keeps retained messages on disk only when persistence is on [R7]. jsonschema does not check `date-time` by default [R16]. iOS Safari has no Vibration API [R12]. The fixes are cheap (PRD §10, R1–R8).

## 1. Domain: home enteral tube feeding

- 93% of carers gave medicines through feeding tubes, but only 62% had professional advice and only 8% had read written information (Alsaeed et al. 2018 [R1]).
- When formal training fell short, carers improvised, sometimes unsafely ([R1]).
- Practical safety problems include dislodgement, **pump inaccuracy**, blockages, storage, and **night-time carer sleep disturbance**. Poor knowledge of **pump alarms** is reported as a main safety issue. ⚠ *Search summary only, unverified* ([R1] and related literature).
- Delays in support after discharge: some patients "were not contacted until seven days or more after discharge" (Ojo 2015 [R2]).

**Inference:** this supports plain-language alarms with pictures and steps (FR-14), a night mode (FR-26), and clinician visibility of exceptions (FR-19). It is not a clinical validation.

## 2. Market: connected enteral pumps

- Kangaroo Connect is described as "the first enteral feeding pump with wireless connectivity". Its portal can "obtain enteral feeding history data, generate Attainment Report of feeding delivery, facilitate remote pump troubleshooting, complete remote pump diagnostic certification … and execute remote software updates." ⚠ *From search summaries of Cardinal Health and distributor pages; the primary page timed out twice* ([R3]).
- Moog EnteraLite Infinity offers bolus, continuous, and intermittent programs. Its standard model is described as lacking Kangaroo Connect's wireless features. ⚠ *Distributor or blog summary* ([R3]).
- **Gap: insufficient data found** on whether any marketed enteral pump supports clinician-initiated remote programming. Check the Kangaroo Connect operator manual (linked in R3) before claiming novelty in the pitch.

## 3. Regulation and standards (context only; none assessed)

- FDA lists enteral pumps among infusion pump types. Reported problems are most often "software defects, user interface issues, and mechanical or electrical failures" ([R4]).
- IEC 60601-2-24:2012 "specifies the requirements for enteral nutrition pumps, infusion pumps …" and includes occlusion alarm thresholds and bolus volume tests. ⚠ *Store and catalogue summaries; the standard is paywalled* ([R18]).
- ISO 80369-3 (ENFit) gives enteral devices connectors that cannot connect to other small-bore connectors such as Luer, to prevent misconnections ([R19]).
- FDA's *Cybersecurity in Medical Devices* guidance (final September 2023, updated June 27, 2025, with a section on §524B "cyber devices") expects an SBOM, vulnerability management, and penetration and fuzz testing for connected devices. ⚠ *Secondary sources* ([R5]).

## 4. Technical stack: documented behaviour that affects the design

| Area | Documented fact | PRD item |
|---|---|---|
| ESP32 MQTT | PubSubClient publishes QoS 0 only; buffer 256 B; keepalive 15 s | R1, R2, M6 |
| Alternative | 256dpi arduino-mqtt supports `publish(..., retained, qos)` and `setWill(..., qos)` | R1(b) |
| Broker | Retained messages are written to disk only with `persistence true` | R3 |
| MQTT semantics | One retained message per topic, delivered on subscribe; the Will is dropped on a graceful DISCONNECT | FR-10, FR-17, R8 |
| Hub MQTT | paho-mqtt 2.x needs `CallbackAPIVersion`; `loop_start()` runs a background thread | R5 |
| Hub async | `call_soon_threadsafe` *must* be used from other threads | R5 |
| Hub SSE | Native `fastapi.sse` since 0.135, with a 15 s keep-alive ping | R5, NFR-P1 |
| Validation | jsonschema `format` is not enforced by default; `date-time` needs `rfc3339-validator` | R4 |
| Audit | SQLite `RAISE(ABORT, …)` in a trigger aborts the statement with `SQLITE_CONSTRAINT` | S7, §8.3 |
| Pump persistence | ESP32 `Preferences` stores data in NVS; names are at most 15 characters | NFR-R2 |
| Family app | `navigator.vibrate` is not on iOS Safari or Firefox Android and needs sticky activation; `speechSynthesis` has `localService` voices | R7, FR-27 |
| Accessibility | WCAG 2.2: 2.5.8 is 24×24 (AA), 2.5.5 is 44×44 (AAA) | NFR-A1 |
| Interop | FHIR R4 `NutritionOrder.enteralFormula` covers rate and max volume | FR-24 |

## Key takeaways

1. **Fix R2 (buffer size) and R1 (QoS 0 events) before the hardware phase.** Both fail only on the ESP32, never in the simulator, which is exactly the kind of failure that turns up on stage.
2. **Turn on Mosquitto persistence and add a hub re-publish (R3).** Otherwise a broker restart silently breaks the "delivered on reconnect" promise.
3. **Demo on an Android phone (R7)**, or the vibration path in the accessibility rules cannot be shown.
4. **Pitch the differentiator carefully:** "caregiver-confirmed, pump-acknowledged remote programming" is not found in public material, but confirm against the Kangaroo Connect manual first.
5. **Name the standards honestly** (IEC 60601-2-24, ISO 80369-3, FDA cybersecurity guidance) under "what a real product would still need".

---

## Sources with documentation excerpts

### [R1] Alsaeed D, Furniss D, Blandford A, Smith F, Orlu M. *Carers' experiences of home enteral feeding: a survey exploring medicines administration challenges and strategies.* J Clin Pharm Ther, 2018
<https://pmc.ncbi.nlm.nih.gov/articles/PMC6849733/> · also <https://onlinelibrary.wiley.com/doi/10.1111/jcpt.12664>

> **Doc excerpt:** "93% of respondents administered medications with enteral feeding tubes, but only 62% had received advice from healthcare professionals and only 8% had received written information."
>
> **Doc excerpt (extracted summary):** 36% never received instructions on preventing tube blockages. Carers improvised, for example dissolving tablets in boiling water or using carbonated drinks to clear blockages.
>
> ⚠ **Search summary:** "Many practical issues may affect patient safety, including accidental or intentional tube dislodgement; pump inaccuracy; frequent tube blockages; inappropriate storage of feed, medicines and equipment, and night-time carer sleep disturbance." / "Poor knowledge of pump alarms was identified as one of the main safety issues among caregivers."

Related, not read in full: Serjeant 2022 meta-synthesis of caregiver experience, *J Hum Nutr Diet* (<https://onlinelibrary.wiley.com/doi/10.1111/jhn.12913>); *Experiences and needs of home caregivers for enteral nutrition: a systematic review of qualitative research* (<https://pubmed.ncbi.nlm.nih.gov/34273248>, blocked by a cookie wall); *Patients' and caregivers' perspective on challenges and outcomes with tube feeding*, 884 respondents, 64% about children (<https://www.sciencedirect.com/science/article/abs/pii/S2405457724000585>, HTTP 403).

### [R2] Ojo O. *The Challenges of Home Enteral Tube Feeding: A Global Perspective.* Nutrients, 2015
<https://pmc.ncbi.nlm.nih.gov/articles/PMC4425159/>

> **Doc excerpt:** common problems include "tube blockage, tube leakage, diarrhoea, overgranulation, vomiting, and pneumonia" … some patients "were not contacted until seven days or more after discharge" and "47% of patients did not receive a delivery until seven or more days after discharge." The article calls for "24-h telephone contacts in cases of emergency".

### [R3] Cardinal Health. *Kangaroo™ Connect Enteral Feeding Pump*
<https://www.cardinalhealth.com/en/product-solutions/medical/enteral-feeding/kangaroo-connect-enteral-feeding-pump.html> · Operator manual: <https://www.cardinalhealth.com/content/dam/corp/web/documents/patient-recovery/Literature/kangaroo-connect-enteral-feeding-pump-operator-manual.pdf> · Patient troubleshooting guide: <https://55933-bcmed.s3.amazonaws.com/bcp/files/flexpaper/pdf/kangaroo_connect_patient_troubleshooting_guide-us.pdf>

> ⚠ **Search summary:** "The Kangaroo™ Connect Enteral Feeding System is the first enteral feeding pump with wireless connectivity and is for use from the hospital to the home." / "The Kangaroo™ Connect Portal can obtain enteral feeding history data, generate Attainment Report of feeding delivery, facilitate remote pump troubleshooting, complete remote pump diagnostic certification for pumps in the field, and execute remote software updates." / "The pump allows users to view previous 72 hours of feeding history."
>
> ⚠ **Search summary (Moog comparison, Vitality Medical blog):** EnteraLite Infinity offers "Bolus, Continuous, and Intermittent feeding programs" and "the standard Infinity pump does not have the same wireless connectivity features as the Kangaroo Connect." <https://www.vitalitymedical.com/blog/moog-infinity-feeding-pump-comparison.html>

### [R4] U.S. FDA. *Infusion Pumps*
<https://www.fda.gov/medical-devices/general-hospital-devices-and-supplies/infusion-pumps>

> **Doc excerpt:** "The most common types of reported problems have been associated with software defects, user interface issues, and mechanical or electrical failures." / "Many of the reported events are related to deficiencies in device design and engineering, which can either create problems themselves or contribute to user error." Pump types listed: "large volume, patient-controlled analgesia (PCA), elastomeric, syringe, enteral, and insulin pumps." From 2005 to 2009, about 56,000 adverse event reports and 87 recalls.

### [R5] U.S. FDA. *Cybersecurity in Medical Devices: Quality System Considerations and Content of Premarket Submissions*
<https://www.fda.gov/medical-devices/digital-health-center-excellence/cybersecurity> · secondary: <https://www.emergobyul.com/news/fda-releases-final-guidance-medical-device-cybersecurity>, <https://aktriva.com/articles/fda-publishes-new-premarket-cybersecurity-guidance/>

> ⚠ **Search summary:** final guidance on September 27, 2023; updated final guidance on June 27, 2025, "adds Section VII to address FDA's recommendations regarding section 524B of the FD&C Act for cyber devices". It expects SBOMs, vulnerability management, and penetration, fuzz, and static or dynamic analysis results in premarket submissions.

### [R6] HiveMQ. *MQTT Essentials* Part 8 (Retained Messages) and Part 9 (Last Will and Testament)
<https://www.hivemq.com/blog/mqtt-essentials-part-8-retained-messages/> · <https://www.hivemq.com/blog/mqtt-essentials-part-9-last-will-and-testament/>

> **Doc excerpt:** "The broker stores only one retained message per topic." / "Each client that subscribes to a topic pattern that matches the topic of the retained message receives the retained message immediately after they subscribe." / To delete one, "publish a retained message with a zero-byte payload".
>
> **Doc excerpt (LWT):** the broker sends the Will on an "I/O error or network failure", a "Failed communication within Keep Alive period", when the "Client closes connection without DISCONNECT", or when the "Broker closes connection due to protocol error". It is discarded if "the client disconnects gracefully using the DISCONNECT message." The recommended pattern is a retained "Offline" Will plus a retained "Online" message on the same topic.

### [R7] Eclipse Mosquitto. *mosquitto.conf(5)*
<https://mosquitto.org/man/mosquitto-conf-5.html>

> **Doc excerpt:** `persistence`: "If enabled, connection, subscription and message data will be written to disk in mosquitto.db at the location dictated by persistence_location." / `autosave_interval`: "The number of seconds that mosquitto will wait between each time it saves the in-memory database to disk." / `allow_anonymous`: "Global boolean value that determines whether clients that connect without providing a username are allowed to connect."

### [R8] Eclipse Paho. *paho-mqtt Python client* docs and 2.0 migration guide
<https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html> · <https://eclipse.dev/paho/files/paho.mqtt.python/html/migrations.html>

> **Doc excerpt:**
> ```python
> Client(callback_api_version=CallbackAPIVersion.VERSION1, client_id='',
>        clean_session=None, userdata=None, protocol=MQTTProtocolVersion.MQTTv311,
>        transport='tcp', reconnect_on_failure=True, manual_ack=False)
> ```
> The parameter "is required". VERSION2 callbacks: `on_connect(client, userdata, connect_flags, reason_code, properties)` and `on_message(client, userdata, message)`. `loop_start()`: "run a background thread that handles network communication". `will_set(topic, payload=None, qos=0, retain=False, properties=None)`.
>
> **Doc excerpt (migration):** "add `mqtt.CallbackAPIVersion.VERSION1` as first argument to `Client()`". We recommend `VERSION2` for new code.

### [R9] FastAPI. *Server-Sent Events*
<https://fastapi.tiangolo.com/tutorial/server-sent-events/>

> **Doc excerpt:** added in **FastAPI 0.135.0**.
> ```python
> from collections.abc import AsyncIterable
> from fastapi import FastAPI
> from fastapi.sse import EventSourceResponse
>
> @app.get("/items/stream", response_class=EventSourceResponse)
> async def sse_items() -> AsyncIterable[Item]:
>     for item in items:
>         yield item
> ```
> "Send a 'keep alive' `ping` comment every 15 seconds when there hasn't been any message, to prevent some proxies from closing the connection". It also sets `Cache-Control: no-cache` and `X-Accel-Buffering: no`. "You don't have to do anything about it, it works out of the box."

### [R10] knolleary. *PubSubClient* (README and `src/PubSubClient.h`)
<https://github.com/knolleary/pubsubclient> · <https://github.com/knolleary/pubsubclient/blob/master/src/PubSubClient.h>

> **Doc excerpt (Limitations):** "It can only publish QoS 0 messages. It can subscribe at QoS 0 or QoS 1." The default maximum message size is 256 bytes including headers, adjustable with `MQTT_MAX_PACKET_SIZE` or `setBufferSize()`. The default keepalive is 15 seconds (`setKeepAlive()`).
>
> **Doc excerpt (header):**
> ```cpp
> // MQTT_MAX_PACKET_SIZE : Maximum packet size. Override with setBufferSize().
> #define MQTT_MAX_PACKET_SIZE 256
> #define MQTT_KEEPALIVE 15
> boolean connect(const char* id, const char* willTopic, uint8_t willQos,
>                 boolean willRetain, const char* willMessage);
> boolean publish(const char* topic, const char* payload, boolean retained);
> boolean subscribe(const char* topic, uint8_t qos);
> boolean setBufferSize(uint16_t size);
> ```
> **Measured locally:** `shared/protocol/examples/prescription.json` is **249 bytes** as compact JSON, before the topic (`pump/pump-001/prescription`, 26 bytes) and the MQTT framing.

### [R10b] 256dpi. *arduino-mqtt*
<https://github.com/256dpi/arduino-mqtt>

> **Doc excerpt:** `bool publish(const char topic[], const String &payload, bool retained, int qos);` · `void setWill(const char topic[], const char payload[], bool retained, int qos);` · "The maximum size for packets being published and received is set by default to 128 bytes. To change the buffer sizes, you need to use `MQTTClient client(256)`". ESP32 examples are included.

### [R11] Espressif. *Arduino-ESP32 Preferences tutorial*
<https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/preferences.html>

> **Doc excerpt:** Preferences is "the replacement for the Arduino EEPROM library" and "uses a portion of the on-board non-volatile memory (NVS) of the ESP32 to store data." `mySketchPrefs.begin("myPrefs", false);` (false means read-write). Namespace and key names are "limited to a maximum of 15 characters." "Preferences works best for storing many small values, rather than a few large values."

### [R12] MDN and Can I use: Vibration and Web Speech
<https://developer.mozilla.org/en-US/docs/Web/API/Navigator/vibrate> · <https://caniuse.com/vibration> · <https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis> · <https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisVoice/localService>

> **Doc excerpt (MDN):** "Sticky user activation is required. The user has to interact with the page or a UI element in order for this feature to work." The feature is "not Baseline because it does not work in some of the most widely-used browsers."
>
> **Doc excerpt (caniuse, retrieved 2026-10-03):** Safari on iOS, "Not supported across all versions (3.2 – 27.2)". Firefox for Android: not supported. Chrome for Android and Samsung Internet: supported.
>
> **Doc excerpt (MDN):** `speak()` "Adds an utterance to the utterance queue". `voiceschanged` fires when the `getVoices()` list changes. `localService` "returns a boolean value indicating whether the voice is supplied by a local speech synthesizer service (`true`), or a remote speech synthesizer service (`false`)".

### [R13] W3C. *Understanding WCAG 2.2 SC 2.5.8 Target Size (Minimum)*
<https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html>

> **Doc excerpt:** "The size of the target for pointer inputs is at least 24 by 24 CSS pixels" (with exceptions). It recommends the stricter 2.5.5 Target Size (Enhanced), 44 by 44, for important controls. Our rule of 48×48 exceeds both.

### [R14] HL7. *FHIR R4 NutritionOrder*
<https://hl7.org/fhir/R4/nutritionorder.html>

> **Doc excerpt:** "A request to supply a diet, formula feeding (enteral) or oral nutritional supplement to a patient/resident." `enteralFormula`: "Feeding provided through the gastrointestinal tract via a tube, catheter, or stoma that delivers nutrition distal to the oral cavity." `administration.rateQuantity`: "The rate of administration of formula via a feeding pump, e.g. 60 mL per hour". `maxVolumeToDeliver`: "The maximum total quantity of formula that may be administered to a subject over the period of time". *(These examples are from the FHIR spec, not guidance.)*

### [R15] SQLite. *CREATE TRIGGER*
<https://www.sqlite.org/lang_createtrigger.html>

> **Doc excerpt:** "When one of RAISE(ROLLBACK,...), RAISE(ABORT,...) or RAISE(FAIL,...) is called during trigger-program execution, the specified ON CONFLICT processing is performed and the current query terminates. An error code of SQLITE_CONSTRAINT is returned to the application, along with the specified error message."
>
> Applied pattern (ours, not from the doc):
> ```sql
> CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit
> BEGIN SELECT RAISE(ABORT, 'audit is append-only (S7)'); END;
> CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit
> BEGIN SELECT RAISE(ABORT, 'audit is append-only (S7)'); END;
> ```

### [R16] python-jsonschema. *Schema Validation: format*
<https://python-jsonschema.readthedocs.io/en/stable/validate/>

> **Doc excerpt:** "By default, as per the specification, no validation is enforced." The `date-time` format "requires rfc3339-validator". "If a dependency is not installed when using a checker that requires it, validation will succeed without throwing an error". Install with `pip install jsonschema[format]` and pass `format_checker=Draft202012Validator.FORMAT_CHECKER`.

### [R17] Python. *asyncio event loop*
<https://docs.python.org/3/library/asyncio-eventloop.html>

> **Doc excerpt:** `loop.call_soon_threadsafe(callback, *args, context=None)`: "A thread-safe variant of call_soon(). When scheduling callbacks from another thread, this function *must* be used, since call_soon() is not thread-safe." "Raises RuntimeError if called on a loop that's been closed."

### [R18] IEC 60601-2-24:2012. *Particular requirements for the basic safety and essential performance of infusion pumps and controllers*
<https://standards.iteh.ai/catalog/standards/iec/160d87f4-23dd-41e7-ba01-aea5145f51e8/iec-60601-2-24-2012> · <https://knowledge.bsigroup.com/products/medical-electrical-equipment-particular-requirements-for-the-basic-safety-and-essential-performance-of-infusion-pumps-and-controllers>

> ⚠ **Search summary (paywalled):** "specifies the requirements for enteral nutrition pumps, infusion pumps, infusion pumps for ambulatory use, syringe or container pumps, volumetric infusion controllers and volumetric infusion pumps." It covers "start-up curves, trumpet curves, occlusion alarm thresholds, and bolus volume verification".

### [R19] GEDSA / Stay Connected. *ENFit (ISO 80369-3)*
<https://stayconnected.org/enfit-faqs/> · <https://enteralconnectors.cookmedical.com/>

> ⚠ **Search summary:** "ISO standard 80369-3, commonly referred to as ENFit, aims to maximize patient safety by reducing the risk of enteral tubing misconnections." The ISO 80369 series assigns "unique, mechanically incompatible connectors for each clinical application." ENFit has been on the market since 2016.

---

## Methodology

- **Connected services:** Google Drive was searched (`enteral`, `smart pump`, `Bio Hack`, `tube feeding`). **No project-relevant files were found.** The only BioHack hit was a different team's 2026 deck on kidney allocation, which was not used. No other data connectors were relevant. Firecrawl and Exa MCP were not configured, so built-in web search and fetch were used instead.
- **Local sources:** every file in the repository scaffold (CLAUDE.md, `docs/*`, `.claude/rules/*`, `shared/protocol/*` and its examples, `firmware/include/*`, `platformio.ini`, `requirements.txt`, `mosquitto.conf`, and the stubs). Example payload sizes were measured locally.
- **Web:** 6 search queries and 24 page fetches. 5 failed: Cardinal Health ×2 (timeout), PubMed (cookie wall), ScienceDirect (403), and pubsubclient.knolleary.net (TLS mismatch, replaced by GitHub).
- **Sub-questions:**
  1. What problems do home tube-feeding families and clinicians face?
  2. What do existing connected enteral pumps offer?
  3. Which standards and regulations frame a real product?
  4. Does the chosen stack (PubSubClient, Mosquitto, paho, FastAPI, jsonschema, SQLite, Web APIs) behave as the plan assumes?
  5. Which accessibility and interoperability references apply?
- **Gaps:** full text of the caregiver-alarm and night-burden literature; the Kangaroo Connect manual (to confirm there is no remote programming); the standards (paywalled).
