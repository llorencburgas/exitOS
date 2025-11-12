


const LoadingSpinner = {
    show: function(text = "Processant...<br>Això pot tardar una mica.") {
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
            // Si ja existeix, actualitzem el text
            document.getElementById('loadingText').innerHTML = text;
        }

        // Mostrem el spinner
        spinner.style.display = 'flex';
    },

    hide: function() {
        const spinner = document.getElementById('loadingSpinner');
        if (spinner) spinner.style.display = 'none';
    }
};
