document.addEventListener("DOMContentLoaded", function () {
    // ✅ Extract token from #access_token and rewrite URL
    const hash = window.location.hash;
    if (hash.startsWith("#access_token=")) {
        const token = hash.replace("#access_token=", "");
        console.log("🔑 Extracted token:", token);

        // Rewrite the URL with ?access_token=
        const newUrl = window.location.pathname + "?access_token=" + token;
        window.history.replaceState({}, "", newUrl);

        // Set token in hidden input field
        document.getElementById("access_token").value = token;
    }

    const form = document.getElementById("reset-password-form");
    const statusMessage = document.getElementById("status-message");

    form.addEventListener("submit", function (e) {
        e.preventDefault();

        const token = document.getElementById("access_token").value;
        const newPassword = document.getElementById("new_password").value;
        const confirmPassword = document.getElementById("confirm_password").value;

        if (!token) {
            statusMessage.innerHTML = `<span style="color: red;">Missing access token.</span>`;
            return;
        }

        if (newPassword !== confirmPassword) {
            statusMessage.innerHTML = `<span style="color: red;">Passwords do not match.</span>`;
            return;
        }

        if (newPassword.length < 8) {
            statusMessage.innerHTML = `<span style="color: red;">Password must be at least 8 characters long.</span>`;
            return;
        }

        // POST to API
        fetch("/api/auth/new-password/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                access_token: token,
                new_password: newPassword,
                confirm_password: confirmPassword
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                statusMessage.innerHTML = `<span style="color: green;">${data.message}</span>`;
                form.reset();
                form.style.display = "none";
            } else {
                statusMessage.innerHTML = `<span style="color: red;">${data.error || "Failed to reset password."}</span>`;
            }
        })
        .catch(err => {
            console.error("Error:", err);
            statusMessage.innerHTML = `<span style="color: red;">An unexpected error occurred.</span>`;
        });
    });
});
