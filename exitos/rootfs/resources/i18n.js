var I18n = (function () {
    var _resources = {};
    var _locale = localStorage.getItem('locale') || 'ca'; // Default to Catalan
    var _elements = [];
    var _onLanguageChangeCallbacks = [];

    function init() {
        console.log("I18n init started. Locale:", _locale);
        loadLocale(_locale);
        bindLanguageSwitcher();
    }

    function loadLocale(locale) {
        if (_resources[locale]) {
            _locale = locale;
            translate();
            updateActiveFlag();
            localStorage.setItem('locale', _locale);
            // Notify callbacks even when using cached locale
            _onLanguageChangeCallbacks.forEach(callback => callback(locale));
            return;
        }

        fetch(`resources/lang/${locale}.json`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Could not load locale ${locale}`);
                }
                return response.json();
            })
            .then(data => {
                _resources[locale] = data;
                _locale = locale;
                translate();
                updateActiveFlag();
                localStorage.setItem('locale', _locale);
                console.log(`Loaded locale: ${locale}`);
                // Notify callbacks
                _onLanguageChangeCallbacks.forEach(callback => callback(locale));
            })
            .catch(error => console.error("Error loading translation:", error));
    }

    function translate() {
        // Translate elements with data-i18n attribute
        var elements = document.querySelectorAll('[data-i18n]');
        elements.forEach(function (element) {
            var key = element.getAttribute('data-i18n');
            var translation = getTranslation(key);
            if (translation) {
                if (element.placeholder) {
                    element.placeholder = translation;
                } else {
                    element.innerHTML = translation;
                }
            } else {
                console.warn(`Missing translation for key: ${key} in locale: ${_locale}`);
            }
        });
    }

    function getTranslation(key) {
        var keys = key.split('.');
        var value = _resources[_locale];
        for (var i = 0; i < keys.length; i++) {
            if (value) {
                value = value[keys[i]];
            } else {
                return null;
            }
        }

        // Support for string formatting with arguments {0}, {1}, etc.
        if (value && arguments.length > 1) {
            for (var i = 1; i < arguments.length; i++) {
                var reg = new RegExp("\\{" + (i - 1) + "\\}", "g");
                value = value.replace(reg, arguments[i]);
            }
        }

        return value;
    }

    function bindLanguageSwitcher() {
        var switcher = document.querySelectorAll('.lang-switch');
        switcher.forEach(function (item) {
            item.addEventListener('click', function (e) {
                e.preventDefault();
                var newLocale = this.getAttribute('data-lang');
                console.log("Switching to:", newLocale);
                loadLocale(newLocale);
            });
        });
    }

    function updateActiveFlag() {
        var items = document.querySelectorAll('.lang-switch');
        items.forEach(function (item) {
            if (item.getAttribute('data-lang') === _locale) {
                item.classList.add('active-lang');
            } else {
                item.classList.remove('active-lang');
            }
        });
    }

    function onLanguageChange(callback) {
        _onLanguageChangeCallbacks.push(callback);
    }

    return {
        init: init,
        translate: translate,
        get: getTranslation,
        onLanguageChange: onLanguageChange
    };
})();

document.addEventListener('DOMContentLoaded', function () {
    I18n.init();
});
