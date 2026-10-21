
/** @odoo-module **/

import {
    Component,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

export class MyAttendanceKiosk extends Component {
    static template = "attendance_kiosk_custom.MyAttendanceKiosk";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.videoContainerRef = useRef("videoContainer");
        this.videoMountRef = useRef("videoMount");
        this.canvasRef = useRef("canvas");

        this.stream = null;
        this.cameraVideo = null;

        this.state = useState({
            loading: true,
            busy: false,
            employee_name: "",
            checked_in: false,
            check_in: false,

            cameraReady: false,
            photoData: "",

            latitude: null,
            longitude: null,
            accuracy: null,

            message: "",
            error: "",
            office_configured: false,
        });

        onWillStart(async () => {
            await this.loadAttendanceStatus();
        });

        onWillUnmount(() => {
            this.stopCamera();
        });
    }

    // =========================================================
    // ATTENDANCE STATUS
    // =========================================================

    async loadAttendanceStatus() {
        this.state.loading = true;
        this.state.error = "";

        try {
            const result = await this.orm.call(
                "hr.attendance",
                "kiosk_get_status",
                []
            );

            if (result && typeof result === "object") {
                this.state.employee_name = result.employee_name || "";

                if (typeof result.checked_in === "boolean") {
                    this.state.checked_in = result.checked_in;
                } else if (typeof result.is_checked_in === "boolean") {
                    this.state.checked_in = result.is_checked_in;
                } else if (typeof result.is_checked_out === "boolean") {
                    this.state.checked_in = !result.is_checked_out;
                } else if (typeof result.status === "string") {
                    this.state.checked_in =
                        result.status === "checked_in" ||
                        result.status === "check_in";
                }

                this.state.check_in = result.check_in || false;

                if ("office_configured" in result) {
                    this.state.office_configured =
                        Boolean(result.office_configured);
                }
            }
        } catch (error) {
            console.error(
                "Unable to load attendance status:",
                error
            );

            this.state.error =
                this.getErrorMessage(error) ||
                "Unable to load attendance status.";
        } finally {
            this.state.loading = false;
        }
    }

    // =========================================================
    // CAMERA
    // =========================================================

    async startCamera() {
        this.state.error = "";
        this.state.message = "";

        if (!navigator.mediaDevices?.getUserMedia) {
            this.state.error =
                "Camera access is unavailable. Use HTTPS or localhost " +
                "and a supported browser.";
            return;
        }

        this.stopCamera();
        this.state.photoData = "";

        try {
            const stream =
                await navigator.mediaDevices.getUserMedia({
                    audio: false,
                    video: {
                        facingMode: "user",
                        width: { ideal: 1280 },
                        height: { ideal: 960 },
                    },
                });

            this.stream = stream;

            const mount = this.videoMountRef.el;

            if (!mount) {
                throw new Error(
                    "Camera display area was not found."
                );
            }

            const video = document.createElement("video");

            video.autoplay = true;
            video.muted = true;
            video.playsInline = true;

            video.setAttribute("playsinline", "");
            video.setAttribute("webkit-playsinline", "");
            video.setAttribute("autoplay", "");
            video.setAttribute("muted", "");

            video.className = "o_kiosk_video is-visible";
            video.style.display = "block";
            video.style.width = "100%";
            video.style.height = "100%";
            video.style.objectFit = "cover";

            video.srcObject = stream;
            this.cameraVideo = video;

            mount.replaceChildren(video);

            await new Promise((resolve, reject) => {
                if (
                    video.readyState >=
                    HTMLMediaElement.HAVE_METADATA
                ) {
                    resolve();
                    return;
                }

                const timeout = window.setTimeout(() => {
                    cleanup();
                    reject(
                        new Error(
                            "Camera initialization timed out."
                        )
                    );
                }, 10000);

                const cleanup = () => {
                    window.clearTimeout(timeout);
                    video.removeEventListener(
                        "loadedmetadata",
                        onReady
                    );
                    video.removeEventListener("error", onError);
                };

                const onReady = () => {
                    cleanup();
                    resolve();
                };

                const onError = () => {
                    cleanup();
                    reject(
                        new Error(
                            "Unable to initialize the camera video."
                        )
                    );
                };

                video.addEventListener(
                    "loadedmetadata",
                    onReady,
                    { once: true }
                );

                video.addEventListener(
                    "error",
                    onError,
                    { once: true }
                );
            });

            await video.play();

            if (!video.videoWidth || !video.videoHeight) {
                throw new Error(
                    "Camera is active, but no video frame is available. " +
                    "Please try again."
                );
            }

            this.state.cameraReady = true;
            this.state.message =
                "Camera is ready. You can take your photo.";
        } catch (error) {
            console.error(
                "Camera initialization failed:",
                error
            );

            this.stopCamera();

            this.state.error =
                this.getErrorMessage(error) ||
                "Unable to start the camera. Check camera permissions.";
        }
    }

    capturePhoto() {
        const video = this.cameraVideo;
        const canvas = this.canvasRef.el;

        if (
            !video ||
            !canvas ||
            !video.videoWidth ||
            !video.videoHeight
        ) {
            this.state.error =
                "Camera is not ready. Please start the camera again.";
            return;
        }

        try {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;

            const context = canvas.getContext("2d");

            if (!context) {
                throw new Error(
                    "Unable to create the photo canvas."
                );
            }

            context.drawImage(
                video,
                0,
                0,
                canvas.width,
                canvas.height
            );

            // Save a static image before stopping the live stream.
            this.state.photoData = canvas.toDataURL(
                "image/jpeg",
                0.85
            );

            this.state.error = "";
            this.state.message =
                "Photo captured. Retake it if you are not satisfied.";

            // Stop the camera but preserve the captured photo.
            this.stopCamera();
        } catch (error) {
            console.error("Photo capture failed:", error);

            this.state.error =
                this.getErrorMessage(error) ||
                "Unable to capture the photo.";
        }
    }

    async retakePhoto() {
        this.state.photoData = "";
        this.state.error = "";
        this.state.message = "";

        await this.startCamera();
    }

    stopCamera() {
        if (this.stream) {
            for (const track of this.stream.getTracks()) {
                track.stop();
            }

            this.stream = null;
        }

        if (this.cameraVideo) {
            this.cameraVideo.pause();
            this.cameraVideo.srcObject = null;
            this.cameraVideo.remove();
            this.cameraVideo = null;
        }

        const mount = this.videoMountRef?.el;

        if (mount) {
            mount.replaceChildren();
        }

        this.state.cameraReady = false;
    }

    // =========================================================
    // GPS
    // =========================================================

    getLocation() {
        this.state.error = "";
        this.state.message = "";

        if (!navigator.geolocation) {
            this.state.error =
                "Geolocation is not supported by this browser.";
            return;
        }

        this.state.message = "Getting GPS location...";

        navigator.geolocation.getCurrentPosition(
            (position) => {
                this.state.latitude =
                    position.coords.latitude;

                this.state.longitude =
                    position.coords.longitude;

                this.state.accuracy =
                    position.coords.accuracy;

                this.state.error = "";

                if (position.coords.accuracy > 100) {
                    this.state.message =
                        "GPS accuracy is low. Try again in an open area.";
                } else {
                    this.state.message =
                        "GPS coordinates received. The server will validate " +
                        "your distance from the office.";
                }
            },
            (error) => {
                console.error("GPS error:", error);

                const messages = {
                    1: "Location permission was denied. Allow location access.",
                    2: "Your location is currently unavailable. Try again.",
                    3: "Getting GPS location timed out. Please try again.",
                };

                this.state.error =
                    messages[error.code] ||
                    "Unable to retrieve GPS location.";

                this.state.message = "";
            },
            {
                enableHighAccuracy: true,
                timeout: 20000,
                maximumAge: 0,
            }
        );
    }

    // =========================================================
    // CHECK IN / CHECK OUT
    // =========================================================

    async submitAttendance() {
        if (this.state.busy || this.state.loading) {
            return;
        }

        this.state.error = "";
        this.state.message = "";

        if (!this.state.photoData) {
            this.state.error = "Please capture your attendance photo first.";
            return;
        }

        if (
            this.state.latitude === null ||
            this.state.longitude === null ||
            this.state.accuracy === null
        ) {
            this.state.error = "Please get your GPS location first.";
            return;
        }

        if (this.state.accuracy > 100) {
            this.state.error =
                "GPS accuracy is too low. Please get your location again.";
            return;
        }

        const action = this.state.checked_in ? "check_out" : "check_in";

        this.state.busy = true;
        this.state.message = "Submitting attendance to the server...";

        try {
            console.info("[Attendance Kiosk] Submitting:", {
                action: action,
                latitude: this.state.latitude,
                longitude: this.state.longitude,
                accuracy: this.state.accuracy,
                photoCaptured: Boolean(this.state.photoData),
            });

            const result = await this.orm.call(
                "hr.attendance",
                "kiosk_submit_attendance",
                [
                    action,
                    this.state.photoData,
                    this.state.latitude,
                    this.state.longitude,
                    this.state.accuracy,
                ]
            );

            console.info("[Attendance Kiosk] Server response:", result);

            if (!result || result.success !== true) {
                throw new Error(
                    result?.message || "The server did not confirm attendance."
                );
            }

            this.state.message =
                result.message ||
                (action === "check_in"
                    ? "Check In recorded successfully."
                    : "Check Out recorded successfully.");

            this.notification.add(this.state.message, {
                type: "success",
            });

            // Clear old photo and GPS after confirmed success.
            this.state.photoData = "";
            this.state.latitude = null;
            this.state.longitude = null;
            this.state.accuracy = null;

            // Refresh status from the server.
            await this.loadAttendanceStatus();

            // Use the server response as a fallback if status refresh fails.
            if (typeof result.checked_in === "boolean") {
                this.state.checked_in = result.checked_in;
            }
        } catch (error) {
            console.error("[Attendance Kiosk] Submission failed:", error);

            const message = this.getErrorMessage(error);

            this.state.error = message ||
                "Attendance failed. Check the Odoo server log for details.";

            this.state.message = "";

            this.notification.add(this.state.error, {
                type: "danger",
            });
        } finally {
            this.state.busy = false;
        }
    }

    getErrorMessage(error) {
        const data = error?.data || {};

        // Odoo can put the actual UserError text in data.arguments.
        if (Array.isArray(data.arguments) && data.arguments.length) {
            const message = data.arguments.find(
                (item) => typeof item === "string" && item.trim()
            );

            if (message) {
                return message;
            }
        }

        if (typeof data.message === "string" &&
            data.message !== "Odoo Server Error") {
            return data.message;
        }

        if (typeof error?.message === "string" &&
            error.message !== "RPC_ERROR") {
            return error.message;
        }

        if (typeof error?.cause?.message === "string") {
            return error.cause.message;
        }

        return "";
    }
}

// Register the Client Action in Odoo.
registry.category("actions").add(
    "attendance_kiosk_custom.my_attendance",
    MyAttendanceKiosk
);
