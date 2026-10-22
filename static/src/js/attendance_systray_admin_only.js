
/** @odoo-module **/

import { registry } from "@web/core/registry";

const systrayRegistry = registry.category("systray");
const attendanceKey = "hr_attendance.attendance_menu";

// Get the existing Odoo Attendance systray item.
const attendanceItem = systrayRegistry.get(attendanceKey);

// Keep the original component and other settings.
// Display it only for Settings Administrators.
systrayRegistry.add(
    attendanceKey,
    {
        ...attendanceItem,
        isDisplayed: (env) => {
            const user = env.services.user;

            return Boolean(
                user &&
                user.isSystem &&
                (
                    typeof attendanceItem.isDisplayed !== "function" ||
                    attendanceItem.isDisplayed(env)
                )
            );
        },
    },
    {
        force: true,
        sequence: 101,
    }
);
