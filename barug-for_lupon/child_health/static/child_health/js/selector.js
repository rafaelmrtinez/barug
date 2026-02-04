(() => {
    const anemia_2_59_seen = document.getElementById("id_anemia_2_59_seen");
    const anemia_2_59_given_iron = document.getElementById("id_anemia_2_59_given_iron");


    anemia_2_59_seen.addEventListener("change", (e) => {
        if (e.target.checked) {
            anemia_2_59_given_iron.disabled = false;
        } else {
            anemia_2_59_given_iron.disabled = true;
            anemia_2_59_given_iron.checked = false;
        }   
    });

    const birth_wt_seen = document.getElementById("id_birth_wt_seen");
    const birth_wt_given_iron = document.getElementById("id_birth_wt_given_iron");

    birth_wt_seen.addEventListener("change", (e) => {
        if (e.target.checked) {
            birth_wt_given_iron.disabled = false;
        } else {
            birth_wt_given_iron.disabled = true;
            birth_wt_given_iron.checked = false;
        }   
    });


})();