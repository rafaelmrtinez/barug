// static/maternal/js/bmiCalculator.js
(() => {
    document.addEventListener("DOMContentLoaded", () => {
        const weightInput = document.getElementById("id_weight_kg");
        const heightInput = document.getElementById("id_height_cm");
        const bmiInput = document.getElementById("id_bmi");
        const bmiCategoryInput = document.getElementById("id_bmi_category");

        if (!weightInput || !heightInput || !bmiInput || !bmiCategoryInput) {
            console.error("One or more BMI-related input fields are missing.");
            return;
        }

        /**
         * Calculate BMI given weight (kg) and height (cm)
         */
        const calculateBMI = (weightKg, heightCm) => {
            if (!weightKg || !heightCm || heightCm <= 0) return null;
            const heightM = heightCm / 100;
            return weightKg / (heightM * heightM);
        };

        /**
         * Determine BMI category based on value
         * (you can adjust thresholds based on your health guideline)
         */
        const getBMICategory = (bmi) => {
            if (bmi === null || isNaN(bmi)) return "N/A";
            if (bmi < 18.5) return "LOW";
            if (bmi < 25) return "NORMAL";
            return "HIGH";
        };

        /**
         * Updates BMI and Category fields in real time
         */
        const updateBMI = () => {
            const weight = parseFloat(weightInput.value);
            const height = parseFloat(heightInput.value);

            // Calculate BMI
            const bmi = calculateBMI(weight, height);
            const bmiRounded = bmi ? bmi.toFixed(2) : "N/A";
            const category = getBMICategory(bmi);

            // Populate results
            bmiInput.value = bmiRounded;
            bmiCategoryInput.value = category;
        };

        // Event listeners for both height and weight inputs
        ["input", "change"].forEach(evt => {
            weightInput.addEventListener(evt, updateBMI);
            heightInput.addEventListener(evt, updateBMI);
        });
    });
})();
