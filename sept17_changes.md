Here's the App Changes doc broken into sections, in plain language:

**1\. Dashboard — 4 main buttons**  
The technician's home screen should have four things: Farm CRM, Alarms, Office Alerts, and To-Do List. (This adds "Alarms" and "Office Alerts" as new items alongside the two that already existed.)

**2\. Notifications — layout**  
Inside each individual notification, put the **farm name at the top** and the **cow at the bottom**. This gives quick context (which farm) before the detail (which cow).

**3\. Notifications — what triggers them**  
Two triggers:

* **Route changes** — if an Administrator changes a technician's route, the technician gets notified.

* **Calendar events** — specifically, Preg Check reminders show up as notifications.

**4\. Alarms (new notification type)**  
A separate feed, distinct from regular notifications, used only for messages **from the farm owner to the technician**.

**5\. Office Alerts (new notification type)**  
Another separate feed, used only for messages **from the Administrator to the technician**.

So the three message channels become: Notifications (system-generated), Alarms (owner → tech), Office Alerts (admin → tech).

**6\. Double Ovsynch / Ovsynch — self-inject option**  
Some farms want to do the final needling themselves (the day before the last insemination day) instead of having the technician do it. So:

* Add a toggle/option per farm: "farmer does this needling himself."

* If enabled, the technician gets a prompt to leave a note telling the farmer which cow needs which hormone.

* The farm also automatically gets a notification with that same info (cow \+ hormone).

**7\. Cow identification**  
Let a cow be identified by **either** her tag number **or** her name — give the option for both.

**8\. Report label changes**  
Simple renames, no logic change:

* Heat Report: "In Heat" → **"Check Heat"**

* Needling Report: rename away from "Needling" (exact new label wasn't specified)

* Pregnancy Report: "Inseminated" → **"Check Pregnancy"**

* Post Calving Report → renamed **"Vaccine Report"**, with an option for farms to self-administer the vaccine

**9\. Dry Report — automation**

* Day 223 post-insemination: cow status auto-changes to **Dry**, and the farm gets notified to stop milking her.

* Day of calving: status auto-changes from **Dry → Fresh**, and the farm gets notified she's Fresh.

**10\. Heat Event — new special case**  
If a cow shows heat at any point (not just the scheduled window), she must be inseminated **that same day** — no waiting for another day.

Want me to also reconcile this against your Master Structure / Status & Report docs (e.g. the Day-70 Monday/Tuesday/Saturday rule) to flag any conflicts before you hand this to a developer?

