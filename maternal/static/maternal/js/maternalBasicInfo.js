(() => {
  document.addEventListener("DOMContentLoaded", () => {
    const personInput = document.getElementById("id_person_id");
    const ageInput = document.getElementById("id_age");

    if (personInput) {
      personInput.removeEventListener("change", handlePersonChange);
      personInput.addEventListener("change", handlePersonChange);
    } else {
      console.error("Element with ID 'id_person_id' not found.");
    }

    if (ageInput) {
      ageInput.removeEventListener("input", handleAgeChange);
      ageInput.addEventListener("input", handleAgeChange);
    } else {
      console.warn("Element with ID 'id_age' not found.");
    }
  });

  function setFieldValue(id, value) {
    const field = document.getElementById(id);
    if (!field) {
      console.warn(`Field with ID '${id}' not found in DOM.`);
      return;
    }

    const finalValue = value && value !== "" ? value : "N/A";
    const wasDisabled = field.disabled;
    if (wasDisabled) field.disabled = false;
    field.value = finalValue;
    if (wasDisabled) field.disabled = true;
  }

  async function handlePersonChange(event) {
    const personId = event.target.value?.trim();

    if (!personId) {
      alert("Please select a valid person first.");
      return;
    }

    try {
      const response = await fetch(`/maternal/find-mother-basic-info/${personId}/`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

      const data = await response.json();
      if (typeof data !== "object" || data === null) {
        throw new Error("Invalid data format received from server.");
      }

      // ✅ Populate all known fields
      setFieldValue("id_family_no", data.family_number);
      setFieldValue("id_date_of_birth", data.date_of_birth);
      setFieldValue("id_age", data.age);
      setFieldValue("id_husband_name", data.spouse_name);
      setFieldValue("id_occupation", data.spouse_occupation);

      // ✅ Assign spouse_id to hidden input
      const husbandIdField = document.getElementById("id_husband_id");
      if (husbandIdField) {
        const wasDisabled = husbandIdField.disabled;
        if (wasDisabled) husbandIdField.disabled = false;
        husbandIdField.value = data.spouse_id || "";
        if (wasDisabled) husbandIdField.disabled = true;
      } else {
        console.warn("Hidden input with ID 'id_husband_id' not found.");
      }

      // ✅ Auto-assign age group
      handleAgeChange({ target: { value: data.age } });

    } catch (error) {
      console.error("Error fetching or displaying mother basic info:", error);
      ["id_family_no", "id_date_of_birth", "id_age", "id_husband_name", "id_occupation"]
        .forEach(id => setFieldValue(id, "N/A"));
    }
  }

  function handleAgeChange(event) {
    const ageGroupField = document.getElementById("id_age_group");
    if (!ageGroupField) {
      console.warn("Field with ID 'id_age_group' not found.");
      return;
    }

    const rawValue = event.target?.value ?? "";
    const age = parseInt(rawValue, 10);

    if (isNaN(age) || age < 10) {
      ageGroupField.value = "N/A";
      return;
    }

    let group = "20–49";
    if (age >= 10 && age <= 14) group = "10–14";
    else if (age >= 15 && age <= 19) group = "15–19";

    const wasDisabled = ageGroupField.disabled;
    if (wasDisabled) ageGroupField.disabled = false;
    ageGroupField.value = group;
    if (wasDisabled) ageGroupField.disabled = true;
  }
})();
