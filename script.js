document.addEventListener('DOMContentLoaded', function() {
    // 1. Get references to the main elements
    const loginForm = document.querySelector('.login-form');
    const registerForm = document.querySelector('.register-form');

    // These are the anchor links inside the forms used to switch views
    const switchToRegisterLink = loginForm.querySelector('p a');
    const switchToLoginLink = registerForm.querySelector('.login-btn');

    // Function to show the Login form and hide Registration
    function showLoginForm() {
        loginForm.style.display = 'block';
        registerForm.style.display = 'none';
    }

    // Function to show the Registration form and hide Login
    function showRegisterForm() {
        loginForm.style.display = 'none';
        registerForm.style.display = 'block';
    }

    // 2. Set Initial State based on potential Flash Messages (for error persistence)
    const flashMessages = document.querySelector('.flash-messages');
    
    // Check if any error messages are present
    if (flashMessages) {
        const errorMessages = flashMessages.querySelectorAll('.flash.error');
        let registrationError = false;

        // Loop through errors to determine where the failure occurred
        errorMessages.forEach(msg => {
            const messageText = msg.textContent.toLowerCase();
            // A failure to register (e.g., email already exists)
            if (messageText.includes('email is already registered') || messageText.includes('must be provided')) {
                registrationError = true;
            }
        });

        // If there was a registration error, keep the registration form open.
        // Otherwise, assume it was a login error or success, and show the login form.
        if (registrationError) {
            showRegisterForm();
        } else {
            showLoginForm();
        }
    } else {
        // Default state: Show the Login form when no messages are present
        showLoginForm();
    }


    // 3. Attach Event Listeners for switching
    
    // Listener to switch from Login to Registration
    if (switchToRegisterLink) {
        switchToRegisterLink.addEventListener('click', function(e) {
            e.preventDefault();
            showRegisterForm();
        });
    }

    // Listener to switch from Registration back to Login
    if (switchToLoginLink) {
        switchToLoginLink.addEventListener('click', function(e) {
            e.preventDefault();
            showLoginForm();
        });
    }
});