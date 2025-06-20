document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.toggle-password').forEach(button => {
        const targetId = button.getAttribute('data-target');
        const passwordField = document.getElementById(targetId);

        if (passwordField) {
            button.addEventListener('click', function () {
                const type = passwordField.getAttribute('type') === 'password' ? 'text' : 'password';
                passwordField.setAttribute('type', type);
                const label = this.querySelector('small');
                label.textContent = type === 'password' ? 'Show' : 'Hide';
            });
        }
    });
});
