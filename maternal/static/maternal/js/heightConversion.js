(() => {
    document.addEventListener("DOMContentLoaded", () => {
    const heightInput = document.getElementById("id_height_cm"); // Django form field id
    const heightFeetDisplay = document.getElementById("height-feet");

    if (heightInput) {
        const convertToFeet = (cm) => {
            const inches = cm / 2.54;
            const feet = Math.floor(inches / 12);
            const remainingInches = Math.round(inches % 12);
            return `${feet}' ${remainingInches}"`;
        };

        heightInput.addEventListener("input", () => {
            const cm = parseFloat(heightInput.value);
            if (!isNaN(cm) && cm > 0) {
                heightFeetDisplay.textContent = `Feet: ${convertToFeet(cm)}`;
            } else {
                heightFeetDisplay.textContent = "Feet: --";
            }
        });
    }
});
})();