function autoFocusInput() {
    const autofocus_input_element = document.querySelector("input#id_{{data.autofocus}}");
    if (autofocus_input_element) {
        autofocus_input_element.classList.remove('error');
        autofocus_input_element.focus();
        const value = autofocus_input_element.value;
        autofocus_input_element.value = '';
        autofocus_input_element.value = value;
        for (const p_element of document.querySelectorAll("p.error[ref=id_{{data.autofocus}}]")) {
            p_element.classList.remove('error');
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
            for (const p_element of document.querySelectorAll(`p.error[ref=${event.target.id}]`)) {
                p_element.classList.remove('error');
            }
        });
        input_element.addEventListener("focusout", (event) => {
            if (event.target.value) {
                event.target.classList.add('not_empty');
            }
            else {
                event.target.classList.remove('not_empty');
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", (event) => {
    if (!document.querySelector("#show_notification_dialog")) {
        autoFocusInput();
    }
    addEventListenerInput();
});