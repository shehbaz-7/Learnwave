document.addEventListener('DOMContentLoaded', function () {
    initializeApp();
});

function initializeApp() {
    initializeTooltips();
    initializeFlashMessageDismissal();
    initializeActiveNavLinks();
    initializeSearchForm();
    initializeKeyboardShortcuts();
    initializeButtonLoadingState(); // <-- Add this new function call
}

// --- NEW: Function to handle button loading states ---
function initializeButtonLoadingState() {
    // This targets any form that doesn't have a 'data-no-loader' attribute
    const formsToInstrument = document.querySelectorAll('form:not([data-no-loader])');
    
    formsToInstrument.forEach(form => {
        form.addEventListener('submit', function (e) {
            // Find the submit button within this specific form
            const submitBtn = form.querySelector('button[type="submit"]');
            
            if (submitBtn) {
                // Check for HTML5 validity; if form is invalid, do nothing
                if (!form.checkValidity()) {
                    return;
                }
                
                // Add loading class and disable to prevent double-clicks
                submitBtn.classList.add('loading');
                submitBtn.disabled = true;

                // Create and prepend a spinner element
                const spinner = document.createElement('span');
                spinner.className = 'spinner-border spinner-border-sm';
                spinner.setAttribute('role', 'status');
                spinner.setAttribute('aria-hidden', 'true');
                submitBtn.prepend(spinner);
            }
        });
    });
}
// --- END NEW FUNCTION ---

function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function initializeFlashMessageDismissal() {
    setTimeout(function () {
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(function (alert) {
            new bootstrap.Alert(alert).close();
        });
    }, 5000);
}

function initializeActiveNavLinks() {
    const currentLocation = window.location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    navLinks.forEach(link => {
        const linkHref = link.getAttribute('href');
        if (currentLocation === linkHref) {
            link.classList.add('active');
            link.setAttribute('aria-current', 'page');
        }
    });
}

function initializeSearchForm() {
    const searchForm = document.querySelector('form[action*="search"]');
    if (!searchForm) return;

    searchForm.addEventListener('submit', function (e) {
        const searchInput = searchForm.querySelector('input[name="q"]');

        if (searchInput && searchInput.value.trim() === '') {
            e.preventDefault(); // Stop the form from submitting
            showAlert('Please enter a search query.', 'warning');

            // --- THIS IS THE FIX ---
            // Manually undo the changes from the global button loader
            // to prevent the button from getting stuck.
            const submitBtn = searchForm.querySelector('button[type="submit"]');
            if (submitBtn) {
                // Use a small timeout to ensure this runs after the
                // other listener has had a chance to disable the button.
                setTimeout(() => {
                    submitBtn.classList.remove('loading');
                    submitBtn.disabled = false;
                    const spinner = submitBtn.querySelector('.spinner-border');
                    if (spinner) {
                        spinner.remove();
                    }
                }, 50); // 50ms is instant to the user but enough for the browser
            }
        }
    });
}

function showAlert(message, type = 'info') {
    const existingAlert = document.querySelector('.bootstrap-alert');
    if (existingAlert) {
        existingAlert.remove();
    }

    const alertContainer = document.createElement('div');
    alertContainer.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show bootstrap-alert`;
    alertContainer.setAttribute('role', 'alert');
    alertContainer.style.position = 'fixed';
    alertContainer.style.top = '80px';
    alertContainer.style.right = '20px';
    alertContainer.style.zIndex = '1055';
    alertContainer.innerHTML = `
        <i class="fas fa-${type === 'error' ? 'exclamation-triangle' : 'info-circle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    document.body.appendChild(alertContainer);

    setTimeout(function () {
        if (alertContainer) {
            new bootstrap.Alert(alertContainer).close();
        }
    }, 5000);
}

function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            const searchInput = document.querySelector('input[name="q"]');
            if (searchInput) {
                searchInput.focus();
            }
        }

        if (e.key === 'Escape') {
            const openModals = document.querySelectorAll('.modal.show');
            openModals.forEach(modal => {
                const bsModal = bootstrap.Modal.getInstance(modal);
                if (bsModal) {
                    bsModal.hide();
                }
            });
        }
    });
}
document.addEventListener('DOMContentLoaded', function () {
    initializeApp();
});

function initializeApp() {
    initializeTooltips();
    initializeFlashMessageDismissal();
    initializeActiveNavLinks();
    initializeSearchForm();
    initializeKeyboardShortcuts();
    initializeButtonLoadingState();
    initializePageTransitions(); // <-- Add the new function call
}

// --- NEW: Function for Page Transitions ---
function initializePageTransitions() {
    const navLinks = document.querySelectorAll('.navbar-nav a.nav-link');
    const mainContainer = document.querySelector('main.container');

    navLinks.forEach(link => {
        // Ensure the link is internal and not a dropdown toggle
        const href = link.getAttribute('href');
        if (href && (href.startsWith('/') || href.startsWith('{{ url_for'))) {
            link.addEventListener('click', function(e) {
                // Prevent immediate navigation
                e.preventDefault();

                // If the link is already active, do nothing
                if (link.classList.contains('active')) {
                    return;
                }
                
                // Add the fade-out class to the main content
                if (mainContainer) {
                    mainContainer.classList.add('fade-out');
                }

                // Wait for the animation to finish, then navigate
                setTimeout(() => {
                    window.location.href = href;
                }, 300); // This duration should match the fadeOut animation time
            });
        }
    });
}
// --- END NEW FUNCTION ---

function initializeButtonLoadingState() {
    const formsToInstrument = document.querySelectorAll('form:not([data-no-loader])');
    
    formsToInstrument.forEach(form => {
        form.addEventListener('submit', function (e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                if (!form.checkValidity()) {
                    return;
                }
                submitBtn.classList.add('loading');
                submitBtn.disabled = true;
                const spinner = document.createElement('span');
                spinner.className = 'spinner-border spinner-border-sm';
                spinner.setAttribute('role', 'status');
                spinner.setAttribute('aria-hidden', 'true');
                submitBtn.prepend(spinner);
            }
        });
    });
}

function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function initializeFlashMessageDismissal() {
    setTimeout(function () {
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(function (alert) {
            new bootstrap.Alert(alert).close();
        });
    }, 5000);
}

function initializeActiveNavLinks() {
    const currentLocation = window.location.pathname;
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    navLinks.forEach(link => {
        const linkHref = link.getAttribute('href');
        if (currentLocation === linkHref) {
            link.classList.add('active');
            link.setAttribute('aria-current', 'page');
        }
    });
}



function showAlert(message, type = 'info') {
    const existingAlert = document.querySelector('.bootstrap-alert');
    if (existingAlert) {
        existingAlert.remove();
    }

    const alertContainer = document.createElement('div');
    alertContainer.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show bootstrap-alert`;
    alertContainer.setAttribute('role', 'alert');
    alertContainer.style.position = 'fixed';
    alertContainer.style.top = '80px';
    alertContainer.style.right = '20px';
    alertContainer.style.zIndex = '1055';
    alertContainer.innerHTML = `
        <i class="fas fa-${type === 'error' ? 'exclamation-triangle' : 'info-circle'} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    document.body.appendChild(alertContainer);

    setTimeout(function () {
        if (alertContainer) {
            new bootstrap.Alert(alertContainer).close();
        }
    }, 5000);
}

function initializeKeyboardShortcuts() {
    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            const searchInput = document.querySelector('input[name="q"]');
            if (searchInput) {
                searchInput.focus();
            }
        }

        if (e.key === 'Escape') {
            const openModals = document.querySelectorAll('.modal.show');
            openModals.forEach(modal => {
                const bsModal = bootstrap.Modal.getInstance(modal);
                if (bsModal) {
                    bsModal.hide();
                }
            });
        }
    });
}
