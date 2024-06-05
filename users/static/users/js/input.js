function autoFocusInput() {
    const first_error_p_element = document.querySelector("p.error[data-ref]");
    if (first_error_p_element && first_error_p_element.dataset.ref) {
        const autofocus_input_element = document.querySelector(`#${first_error_p_element.dataset.ref}`);
        if (autofocus_input_element) {
            autofocus_input_element.classList.remove('error');
            autofocus_input_element.focus();
            const value = autofocus_input_element.value;
            autofocus_input_element.value = '';
            autofocus_input_element.value = value;
            for (const p_element of document.querySelectorAll(`p.error[data-ref=${autofocus_input_element.id}]`)) {
                p_element.classList.remove('error');
            }
        }
    }
}

function addEventListenerInput() {
    for (const input_element of document.getElementsByTagName("input")) {
        input_element.addEventListener("invalid", (event) => {
            event.target.setCustomValidity("");
            event.target.title = "";
            if (event.target.validity.valueMissing) {
                event.target.setCustomValidity("Vui lòng điền vào trường này.");
                event.target.title = "Vui lòng điền vào trường này.";
            }
        });
        input_element.addEventListener("input", (event) => {
            event.target.setCustomValidity("");
            event.target.title = event.target.placeholder;
        });
        input_element.addEventListener("focusin", (event) => {
            event.target.classList.remove('error');
            for (const p_element of document.querySelectorAll(`p.error[data-ref=${event.target.id}]`)) {
                p_element.classList.remove('error');
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", (event) => {
    for (const input_element of document.querySelectorAll("input")) {
        input_element.classList.add('apply');
    }
    for (const p_element of document.querySelectorAll("p.error[data-ref]")) {
        p_element.classList.add('apply');
    }
    if (!document.querySelector("#show_notification_dialog")) {
        autoFocusInput();
    }
    addEventListenerInput();
});