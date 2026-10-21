/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MyAttendanceKiosk extends Component {
    static template = "attendance_kiosk_custom.MyAttendanceKiosk";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.videoRef = useRef("video");
        this.canvasRef = useRef("canvas");
        this.state = useState({
            loading: true, busy: false, employee_name: "", checked_in: false, check_in: false,
            cameraReady: false, photoData: "", latitude: null, longitude: null, accuracy: null,
            error: "", office_configured: false,
        });
        this.stream = null;
        onWillStart(async () => await this.refreshStatus());
        onWillUnmount(() => this.stopCamera());
    }

    async refreshStatus() {
        this.state.loading = true;
        try {
            const result = await this.orm.call("hr.attendance", "kiosk_get_status", []);
            Object.assign(this.state, result);
            this.state.error = "";
        } catch (error) {
            this.state.error = error.message?.data?.message || error.message || "Unable to load attendance status.";
        } finally {
            this.state.loading = false;
        }
    }

    async startCamera() {
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

            const stream = await navigator.mediaDevices.getUserMedia({
                audio: false,
                video: {
                    facingMode: "user",
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                },
            });

            this.stream = stream;

            // Wait until Owl has rendered the video element.
            await new Promise((resolve) => requestAnimationFrame(resolve));

            const video = this.videoRef.el;

            if (!video) {
                throw new Error("Camera preview element was not found.");
            }

            video.setAttribute("playsinline", "");
            video.setAttribute("webkit-playsinline", "");
            video.muted = true;
            video.autoplay = true;

            // Listen for metadata before attaching the stream.
            const metadataReady = video.readyState >= 1
                ? Promise.resolve()
                : new Promise((resolve, reject) => {
                    const onLoaded = () => {
                        cleanup();
                        resolve();
                    };

                    const onError = () => {
                        cleanup();
                        reject(new Error(
                            "Unable to load camera video metadata."
                        ));
                    };

                    const cleanup = () => {
                        video.removeEventListener(
                            "loadedmetadata", onLoaded
                        );
                        video.removeEventListener("error", onError);
                    };

                    video.addEventListener(
                        "loadedmetadata", onLoaded, { once: true }
                    );
                    video.addEventListener(
                        "error", onError, { once: true }
                    );
                });

            video.srcObject = stream;

            await video.play();
            await metadataReady;

            if (!video.videoWidth || !video.videoHeight) {
                throw new Error(
                    "Camera started, but no video frame is available. Please retry."
                );
            }

            // Mark preview ready only after video playback works.
            this.state.cameraReady = true;
            this.state.error = "";

        } catch (error) {
            this.stopCamera();

            this.state.error =
                error.name === "NotAllowedError"
                    ? "Camera permission denied. Allow camera access in your browser."
                    : error.name === "NotReadableError"
                    ? "Camera is being used by another application. Close it and retry."
                    : error.message || "Could not start camera. Please retry.";
        }
    }

    stopCamera() {
        if (this.stream) {
            for (const track of this.stream.getTracks()) {
                track.stop();
            }
            this.stream = null;
        }

        const video = this.videoRef?.el;

        if (video) {
            video.pause();
            video.srcObject = null;
        }
    }

    capturePhoto() {
        const video = this.videoRef.el;
        const canvas = this.canvasRef.el;
        if (!video || !canvas || !video.videoWidth) {
            this.state.error = "Camera is not ready. Start the camera and try again.";
            return;
        }
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
        this.state.photoData = canvas.toDataURL("image/jpeg", 0.82);
        this.state.error = "";
        this.notification.add("Photo captured.", { type: "success" });
    }

    async getLocation() {
        this.state.error = "";
        this.state.latitude = null;
        this.state.longitude = null;
        this.state.accuracy = null;
        if (!navigator.geolocation) {
            this.state.error = "Geolocation is not supported by this browser.";
            return;
        }
        try {
            const position = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true, timeout: 20000, maximumAge: 0,
                });
            });
            this.state.latitude = position.coords.latitude;
            this.state.longitude = position.coords.longitude;
            this.state.accuracy = position.coords.accuracy;
            if (position.coords.accuracy > 100) {
                this.state.error = `GPS accuracy is ${Math.round(position.coords.accuracy)} m. Retry where the GPS signal is clearer.`;
            }
        } catch (error) {
            const messages = {
                1: "Location permission was denied. Allow location access in your browser.",
                2: "Location is unavailable. Check device location services.",
                3: "GPS request timed out. Please retry.",
            };
            this.state.error = messages[error.code] || error.message || "Unable to obtain GPS location.";
        }
    }

    async submitAttendance() {
        if (!this.state.photoData) {
            this.state.error = "A photo is required. Start the camera and capture a photo first.";
            return;
        }
        if (this.state.latitude === null || this.state.longitude === null || this.state.accuracy === null) {
            this.state.error = "GPS location is required. Click Get GPS Location first.";
            return;
        }
        if (this.state.accuracy > 100) {
            this.state.error = "GPS accuracy must be 100 meters or better.";
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            const action = this.state.checked_in ? "check_out" : "check_in";
            const result = await this.orm.call("hr.attendance", "kiosk_submit_attendance", [
                action, this.state.photoData, this.state.latitude, this.state.longitude, this.state.accuracy,
            ]);
            this.notification.add(result.message || "Attendance saved.", { type: "success" });
            this.state.photoData = "";
            this.state.latitude = this.state.longitude = this.state.accuracy = null;
            this.stopCamera();
            await this.refreshStatus();
        } catch (error) {
            this.state.error = error.message?.data?.message || error.message || "Attendance was rejected.";
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("attendance_kiosk_custom.my_attendance", MyAttendanceKiosk);
