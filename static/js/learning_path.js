function initializeLearningPath(docId) {
    const pathTitleEl = document.getElementById('path-title');
    const stepsListEl = document.getElementById('steps-list');
    const iframeEl = document.getElementById('content-iframe');
    const loaderOverlayEl = document.getElementById('loader-overlay');
    const loaderTextEl = document.getElementById('loader-text');

    let currentSteps = [];

    // Fetches the learning path structure from the backend
    async function fetchPathStructure() {
        try {
            const response = await fetch(`/learning-path/generate/${docId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                throw new Error('Network response was not ok.');
            }

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            
            currentSteps = data.steps;
            renderSidebar(data.path_title, data.steps);
            // Automatically load the first step
            if (data.steps && data.steps.length > 0) {
                loadStepContent(data.steps[0].step);
            }

        } catch (error) {
            console.error('Failed to fetch learning path structure:', error);
            pathTitleEl.innerHTML = 'Error';
            stepsListEl.innerHTML = `<div class="alert alert-danger">Could not generate the learning path. ${error.message}</div>`;
            hideLoader();
        }
    }

    // Renders the sidebar with the path title and steps
    function renderSidebar(title, steps) {
        pathTitleEl.textContent = title;
        stepsListEl.innerHTML = ''; // Clear skeleton loader

        steps.forEach(step => {
            const stepEl = document.createElement('div');
            stepEl.className = 'step-item mb-2';
            stepEl.dataset.step = step.step;
            stepEl.innerHTML = `
                <h5 class="mb-1"><span class="step-number">Step ${step.step}:</span> ${step.title}</h5>
                <p class="mb-0 small text-muted">${step.description}</p>
            `;
            stepsListEl.appendChild(stepEl);
        });
    }

    // Loads the interactive content for a given step into the iframe
    function loadStepContent(stepNumber) {
        // Update active state in sidebar
        document.querySelectorAll('.step-item').forEach(el => {
            el.classList.toggle('active', el.dataset.step == stepNumber);
        });

        showLoader(`Loading Step ${stepNumber}...`);
        
        // Setting src triggers the load; security handled by sandbox attribute
        iframeEl.src = `/learning-path/step-content/${docId}/${stepNumber}`;
    }
    
    // Show/hide the loader overlay
    function showLoader(message) {
        loaderTextEl.textContent = message;
        loaderOverlayEl.style.opacity = '1';
        loaderOverlayEl.style.display = 'flex';
    }

    function hideLoader() {
        loaderOverlayEl.style.opacity = '0';
        setTimeout(() => {
            loaderOverlayEl.style.display = 'none';
        }, 300); // Match transition time
    }

    // Event Delegation for clicking on steps
    stepsListEl.addEventListener('click', (e) => {
        const stepItem = e.target.closest('.step-item');
        if (stepItem && stepItem.dataset.step) {
            const stepNumber = parseInt(stepItem.dataset.step, 10);
            loadStepContent(stepNumber);
        }
    });
    
    // Hide loader when iframe content has finished loading
    iframeEl.addEventListener('load', () => {
        hideLoader();
    });

    // Initial call to start the process
    fetchPathStructure();
}