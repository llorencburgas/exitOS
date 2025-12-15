(function () {
    function cssVar(name){
        return getComputedStyle(document.documentElement)
            .getPropertyValue(name)
            .trim();
    }

    window.PlotlyTheme = {
        layout() {
            return {
                paper_bgcolor: cssVar('--plot-paper'),
                plot_bgcolor: cssVar('--plot-bg'),
                font:{
                    color: cssVar('--plot-text')
                },
                xaxis:{
                    gridcolor: cssVar('--plot-grid'),
                    zerolinecolor: cssVar('--plot-grid')
                },
                yaxis:{
                    gridcolor: cssVar('--plot-grid'),
                    zerolinecolor: cssVar('--plot-grid')
                }
            };
        },

        mergeLayout(customLayout = {}){
            return {
                ...customLayout,
                ...this.layout(),
                xaxis: {
                    ...(customLayout.xaxis || {}),
                    ...(this.layout().xaxis)
                },
                yaxis: {
                    ...(customLayout.yaxis || {}),
                    ...(this.layout().yaxis)
                }
            };
        },

        applyToPlot(containerId){
            Plotly.relayout(containerId, this.layout());
        },

        applyToAll(){
            document.querySelectorAll('.js-plotly-plot').forEach(el => {
                Plotly.relayout(el, this.layout());
            });
        }
    };
})();