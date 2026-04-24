document.addEventListener('DOMContentLoaded', function() {
    const trigger = document.getElementById('profile-trigger');
    const menu = document.getElementById('profile-menu');

    // Toggle menu on click
    trigger.addEventListener('click', function(e) {
        menu.classList.toggle('show');
        e.stopPropagation(); // Prevents the click from reaching the 'window' listener below
    });

    // Close the menu if the user clicks anywhere else on the screen
    window.addEventListener('click', function() {
        if (menu.classList.contains('show')) {
            menu.classList.remove('show');
        }
    });
});