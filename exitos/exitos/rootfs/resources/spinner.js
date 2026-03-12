


const LoadingSpinner = {
    show: function (text = null) {
        // Obtenir text traduït si no s'especifica un de concret
        if (!text) {
            text = (typeof I18n !== 'undefined' && I18n.get('spinner.loading'))
                ? I18n.get('spinner.loading')
                : "Processant...<br>Això pot tardar una mica.";
        }

        // Comprovem si el spinner ja existeix
        let spinner = document.getElementById('loadingSpinner');

        if (!spinner) {
            // Si no existeix, el creem
            spinner = document.createElement('div');
            spinner.id = 'loadingSpinner';
            spinner.innerHTML = `
                <div class="spinner"></div>
                <p id="loadingText">${text}</p>
            `;
            document.body.appendChild(spinner);
        } else {
            // Si ja existeix, actualitzem el text independentment de si s'acaba de crear o no
            document.getElementById('loadingText').innerHTML = text;
        }

        // Mostrem el spinner
        spinner.style.display = 'flex';
    },

    hide: function () {
        const spinner = document.getElementById('loadingSpinner');
        if (spinner) spinner.style.display = 'none';
    }
};
