/**
 * AJAX form submission component.
 *
 * Handles two contexts:
 *
 * 1. FormPage — [data-form-page]
 *    The form is already rendered in the page. On submit, posts via fetch
 *    and replaces the form with the thank-you message on success.
 *
 * 2. SignupBlock (wagtail_forms variant) — [data-signup-block]
 *    Fetches the form HTML from the linked FormPage URL, renders it inline,
 *    then handles AJAX submission the same way.
 *
 * Data attributes:
 *   [data-form-page]       — FormPage container
 *   [data-form-container]  — wrapper around the <form>
 *   [data-thank-you]       — hidden element shown on success
 *   [data-signup-block]    — SignupBlock container
 *   [data-form-url]        — URL of the FormPage to fetch the form from
 */
class FormAjax {
    static init() {
        FormAjax._initFormPages();
        FormAjax._initSignupBlocks();
    }

    /**
     * Attach AJAX submit handling to all [data-form-page] containers.
     */
    static _initFormPages() {
        const containers = document.querySelectorAll('[data-form-page]');
        containers.forEach((container) => {
            const form = container.querySelector('form');
            if (!form) { return; }
            FormAjax._attachSubmitHandler(form, container);
        });
    }

    /**
     * For each [data-signup-block], fetch the form from the linked FormPage
     * and render it inline, then attach AJAX submit handling.
     */
    static _initSignupBlocks() {
        const blocks = document.querySelectorAll('[data-signup-block]');
        blocks.forEach((block) => {
            const formUrl = block.getAttribute('data-form-url');
            if (!formUrl) { return; }
            FormAjax._loadSignupForm(block, formUrl);
        });
    }

    /**
     * Fetch the FormPage HTML, extract the <form>, and insert it into the
     * signup block container.
     */
    static async _loadSignupForm(block, formUrl) {
        // Only allow relative or HTTP(S) URLs
        if (!formUrl.startsWith('/') && !formUrl.startsWith('http')) { return; }

        try {
            const response = await fetch(formUrl, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            });
            if (!response.ok) {
                FormAjax._showFetchFallback(block, formUrl);
                return;
            }

            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const remoteForm = doc.querySelector('[data-form-container] form') || doc.querySelector('form');
            if (!remoteForm) {
                FormAjax._showFetchFallback(block, formUrl);
                return;
            }

            // Replace the placeholder content with the actual form
            const formContainer = block.querySelector('[data-form-container]');
            if (formContainer) {
                formContainer.innerHTML = '';
                formContainer.appendChild(remoteForm);
            }

            // Update the form action to post to the original FormPage URL
            remoteForm.setAttribute('action', formUrl);

            FormAjax._attachSubmitHandler(remoteForm, block);
        } catch (error) {
            // On fetch failure, show a fallback link so the user can still sign up
            FormAjax._showFetchFallback(block, formUrl);
        }
    }

    /**
     * Attach an AJAX submit handler to a form element.
     * On success, hides the form container and shows the thank-you message.
     * On validation errors, re-renders the form with error messages.
     */
    static _attachSubmitHandler(form, container) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            const submitButton = form.querySelector('[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
            }

            try {
                const formData = new FormData(form);
                const response = await fetch(form.action, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });

                // Parse responses for both 2xx (success) and 400 (validation errors).
                // Only skip parsing for 5xx or other unexpected status codes.
                if (response.ok || response.status === 400) {
                    const contentType = response.headers.get('content-type') || '';

                    if (contentType.includes('application/json')) {
                        const data = await response.json();
                        if (data.success) {
                            FormAjax._showSuccess(container);
                        } else if (data.errors) {
                            FormAjax._showErrors(form, data.errors);
                            if (submitButton) { submitButton.disabled = false; }
                        } else {
                            // Unexpected JSON shape — re-enable so user can retry
                            if (submitButton) { submitButton.disabled = false; }
                        }
                    } else {
                        // Wagtail's FormPage returns HTML — a successful submission
                        // redirects or re-renders. If we get HTML back after a POST,
                        // check if it contains the thank-you text (form was processed)
                        // or validation errors (form needs correction).
                        const html = await response.text();
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(html, 'text/html');

                        // If the response contains [data-thank-you] visible or no
                        // form errors, treat it as success.
                        const hasErrors = doc.querySelector('.errorlist, .error');
                        if (hasErrors) {
                            // Re-render the form with server-side errors
                            const newForm = doc.querySelector('[data-form-container] form') ||
                                            doc.querySelector('form');
                            if (newForm) {
                                const formContainer = container.querySelector('[data-form-container]');
                                if (formContainer) {
                                    formContainer.innerHTML = '';
                                    formContainer.appendChild(newForm);
                                    FormAjax._attachSubmitHandler(newForm, container);
                                }
                            } else {
                                // Could not extract new form — re-enable so user can retry
                                if (submitButton) { submitButton.disabled = false; }
                            }
                        } else {
                            FormAjax._showSuccess(container);
                        }
                    }
                } else {
                    // Server error (5xx etc.) — re-enable the button so user can retry
                    if (submitButton) { submitButton.disabled = false; }
                }
            } catch (error) {
                // Network error — re-enable the button so user can retry
                if (submitButton) { submitButton.disabled = false; }
            }
        });
    }

    /**
     * Hide the form container and show the thank-you message.
     */
    static _showSuccess(container) {
        const formContainer = container.querySelector('[data-form-container]');
        const thankYou = container.querySelector('[data-thank-you]');

        if (formContainer) { formContainer.classList.add('hidden'); }
        if (thankYou) { thankYou.classList.remove('hidden'); }
    }

    /**
     * Display validation errors returned as JSON on the form fields.
     * Handles per-field errors and __all__ (non-field) errors.
     */
    static _showErrors(form, errors) {
        // Clear any previous error messages we added
        form.querySelectorAll('[data-ajax-error]').forEach((el) => el.remove());

        for (const [fieldName, messages] of Object.entries(errors)) {
            const errorList = document.createElement('ul');
            errorList.setAttribute('data-ajax-error', '');
            errorList.setAttribute('role', 'alert');

            if (fieldName === '__all__') {
                // Non-field errors — display at the top of the form
                errorList.className = 'mb-4 text-sm text-error-600';
                messages.forEach((msg) => {
                    const li = document.createElement('li');
                    li.textContent = typeof msg === 'string' ? msg : msg.message || String(msg);
                    errorList.appendChild(li);
                });
                form.insertBefore(errorList, form.firstChild);
                continue;
            }

            const field = form.querySelector(`[name="${CSS.escape(fieldName)}"]`);
            if (!field) { continue; }

            errorList.className = 'mb-1 text-sm text-error-600';
            messages.forEach((msg) => {
                const li = document.createElement('li');
                li.textContent = typeof msg === 'string' ? msg : msg.message || String(msg);
                errorList.appendChild(li);
            });
            field.parentElement.insertBefore(errorList, field);
        }
    }

    /**
     * Escape HTML entities to prevent XSS when inserting user-provided text.
     */
    static _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Replace the "Loading form..." text with a fallback link when the
     * form cannot be fetched.
     */
    static _showFetchFallback(block, formUrl) {
        const formContainer = block.querySelector('[data-form-container]');
        if (formContainer && formUrl) {
            formContainer.innerHTML =
                '<p class="text-sm text-neutral-500">' +
                '<a href="' + FormAjax._escapeHtml(formUrl) +
                '" class="underline">' +
                FormAjax._escapeHtml(formUrl) + '</a></p>';
        }
    }
}

export default FormAjax;
