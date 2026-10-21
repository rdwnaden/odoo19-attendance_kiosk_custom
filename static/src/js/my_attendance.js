
/** @odoo-module **/

import {
    Component,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MyAttendanceKiosk extends Component {
    static template = "attendance_kiosk_custom.MyAttendanceKiosk";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        // The video element is created dynamically for iOS WebKit testing.
        this.videoContainerRef = useRef("videoContainer");
        this.canvasRef = useRef("canvas");

        this.stream = null;
        this.cameraVideo = null;
        this.cameraStarting = false;

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
            error: "",
            office_configured: false,
        });

        onWillStart(async () => {
            await this.refreshStatus();
        });

        onWillUnmount(() => {
            this.stopCamera();
        });
    }

    async refreshStatus() {
        this.state.loading = true;

        try {
            const result = await this.orm.call(
                "hr.attendance",
                "kiosk_get_status",
                []
            );

            Object.assign(this.state, result);
            this.state.error = "";
        } catch (error) {
            this.state.error =
                error.message?.data?.message ||
                error.message ||
                "Unable to load attendance status.";
        } finally {
            this.state.loading = false;
        }
    }

    async startCamera() {
        if (this.cameraStarting || this.state.busy) {
            return;
        }

        this.cameraStarting = true;
        this.state.error = "";
        this.state.photoData = "";
        this.state.cameraReady = false;

        try {
            if (!navigator.mediaDevices?.getUserMedia) {
                throw new Error(
                    "Camera requires HTTPS and a supported browser."
                );
            }

            this.stopCamera();

            if (!this.videoContainerRef.el) {
                throw new Error(
                    "Camera container is unavailable. Please reload the page."
                );
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    facingMode: "user",
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                },
            });

            this.stream = stream;

            // The component may have been removed while permission was pending.
            if (!this.videoContainerRef.el) {
                this.stopCamera();
                return;
            }

            const video = document.createElement("video");

            video.autoplay = true;
            video.muted = true;
            video.playsInline = true;

            video.setAttribute("autoplay", "");
            video.setAttribute("muted", "");
            video.setAttribute("playsinline", "");
            video.setAttribute("webkit-playsinline", "");

            video.className = "o_kiosk_video is-visible";

            video.style.display = "block";
            video.style.width = "100%";
            video.style.height = "100%";
            video.style.objectFit = "contain";
            video.style.backgroundColor = "#111";

            this.cameraVideo = video;
            this.videoContainerRef.el.appendChild(video);

            // Wait for metadata without relying on a stale Owl video reference.
            const metadataReady = new Promise((resolve, reject) => {
                if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
                    resolve();
                    return;
                }

                const timeout = setTimeout(() => {
                    cleanup();
                    reject(
                        new Error("Camera metadata timed out. Please retry.")
                    );
                }, 10000);

                const onLoaded = () => {
                    cleanup();
                    resolve();
                };

                const onError = () => {
                    cleanup();
                    reject(
                        new Error("Unable to initialize the camera preview.")
                    );
                };

                const cleanup = () => {
                    clearTimeout(timeout);
                    video.removeEventListener("loadedmetadata", onLoaded);
                    video.removeEventListener("error", onError);
                };

                video.addEventListener("loadedmetadata", onLoaded, {
                    once: true,
                });

                video.addEventListener("error", onError, {
                    once: true,
                });
            });

            video.srcObject = stream;

            await video.play();
            await metadataReady;

            // Wait for dimensions and a presented frame.
            await new Promise((resolve, reject) => {
                let attempts = 0;

                const checkFrame = () => {
                    if (
                        !this.cameraVideo ||
                        this.cameraVideo !== video ||
                        !this.stream
                    ) {
                        reject(new Error("Camera preview was interrupted."));
                        return;
                    }

                    if (
                        video.videoWidth > 0 &&
                        video.videoHeight > 0
                    ) {
                        resolve();
                        return;
                    }

                    attempts += 1;

                    if (attempts >= 60) {
                        reject(
                            new Error(
                                "No camera frame received. Please stop and retry."
                            )
                        );
                        return;
                    }

                    requestAnimationFrame(checkFrame);
                };

                checkFrame();
            });

            // Trigger a WebKit layout refresh after attaching the stream.
            video.style.visibility = "hidden";
            void video.offsetHeight;
            video.style.visibility = "visible";

            await video.play();

            this.state.cameraReady = true;
            this.state.error = "";

        } catch (error) {
            this.stopCamera();

            this.state.error =
                error.name === "NotAllowedError"
                    ? "Camera permission denied. Allow camera access in browser settings."
                    : error.name === "NotReadableError"
                    ? "Camera is being used by another application. Close it and retry."
                    : error.message ||
                      "Could not start camera. Please retry.";
        } finally {
            this.cameraStarting = false;
        }
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

        this.state.cameraReady = false;
    }

    capturePhoto() {
        const video = this.cameraVideo;
        const canvas = this.canvasRef.el;

        if (
            !video ||
            !canvas ||
            !this.state.cameraReady ||
            !video.videoWidth ||
            !video.videoHeight
        ) {
            this.state.error =
                "Camera preview is not ready. Start the camera and retry.";
            return;
        }

        try {
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;

            const context = canvas.getContext("2d");

            if (!context) {
                throw new Error("Unable to initialize photo capture.");
            }

            context.drawImage(
                video,
                0,
                0,
                canvas.width,
                canvas.height
            );

            this.state.photoData = canvas.toDataURL("image/jpeg", 0.82);
            this.state.error = "";

            this.notification.add("Photo captured.", {
                type: "success",
            });
        } catch (error) {
            this.state.error =
                error.message || "Unable to capture photo.";
        }
    }

    async getLocation() {
        this.state.error = "";
        this.state.latitude = null;
        this.state.longitude = null;
        this.state.accuracy = null;

        if (!navigator.geolocation) {
            this.state.error =
                "Geolocation is not supported by this browser.";
            return;
        }

        try {
            const position = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true,
                    timeout: 20000,
                    maximumAge: 0,
                });
            });

            this.state.latitude = position.coords.latitude;
            this.state.longitude = position.coords.longitude;
            this.state.accuracy = position.coords.accuracy;

            if (position.coords.accuracy > 100) {
                this.state.error =
                    `GPS accuracy is ${Math.round(position.coords.accuracy)} m. ` +
                    "Retry where the GPS signal is clearer.";
            }
        } catch (error) {
            const messages = {
                1: "Location permission was denied. Allow location access in your browser.",
                2: "Location is unavailable. Check device location services.",
                3: "GPS request timed out. Please retry.",
            };

            this.state.error =
                messages[error.code] ||
                error.message ||
                "Unable to obtain GPS location.";
        }
    }

    async submitAttendance() {
        if (!this.state.photoData) {
            this.state.error =
                "A photo is required. Start the camera and capture a photo first.";
            return;
        }

        if (
            this.state.latitude === null ||
            this.state.longitude === null ||
            this.state.accuracy === null
        ) {
            this.state.error =
                "GPS location is required. Click Get GPS Location first.";
            return;
        }

        if (this.state.accuracy > 100) {
            this.state.error =
                "GPS accuracy must be 100 meters or better.";
            return;
        }

        this.state.busy = true;
        this.state.error = "";

        try {
            const action = this.state.checked_in
                ? "check_out"
                : "check_in";

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

            this.notification.add(
                result.message || "Attendance saved.",
                { type: "success" }
            );

            this.state.photoData = "";
            this.state.latitude = null;
            this.state.longitude = null;
            this.state.accuracy = null;

            this.stopCamera();

            await this.refreshStatus();
        } catch (error) {
            this.state.error =
                error.message?.data?.message ||
                error.message ||
                "Attendance was rejected.";
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add(
    "attendance_kiosk_custom.my_attendance",
    MyAttendanceKiosk
);
