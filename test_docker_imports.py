#!/usr/bin/env python3
"""
Script de prueba para verificar que las importaciones funcionan correctamente en el entorno Docker
"""

import sys
import os

def test_local_imports():
    """Prueba las importaciones en entorno local"""
    print("=== Probando importaciones en entorno local ===")
    try:
        # Simular el entorno local
        sys.path.append(os.path.join(os.path.dirname(__file__), 'exitos', 'rootfs'))
        
        import forecast.Forecaster as ForecasterModule
        import forecast.ForecasterManager as ForecatManager
        import forecast.OptimalScheduler as OptimalSchedulerModule
        
        forecast = ForecasterModule.Forecaster(debug=True)
        optimalScheduler = OptimalSchedulerModule.OptimalScheduler()
        
        print("✓ Importaciones locales exitosas")
        print(f"✓ Forecaster creado: {type(forecast)}")
        print(f"✓ OptimalScheduler creado: {type(optimalScheduler)}")
        return True
        
    except Exception as e:
        print(f"✗ Error en importaciones locales: {e}")
        return False

def test_docker_imports():
    """Prueba las importaciones en entorno Docker"""
    print("\n=== Probando importaciones en entorno Docker ===")
    try:
        # Simular el entorno Docker
        forecast_path = os.path.join(os.path.dirname(__file__), 'exitos', 'rootfs', 'forecast')
        sys.path.insert(0, forecast_path)
        
        from Forecaster import Forecaster
        from ForecasterManager import obtainmeteoData
        from OptimalScheduler import OptimalScheduler
        
        forecast = Forecaster(debug=True)
        optimalScheduler = OptimalScheduler()
        
        print("✓ Importaciones Docker exitosas")
        print(f"✓ Forecaster creado: {type(forecast)}")
        print(f"✓ OptimalScheduler creado: {type(optimalScheduler)}")
        return True
        
    except Exception as e:
        print(f"✗ Error en importaciones Docker: {e}")
        return False

if __name__ == "__main__":
    local_ok = test_local_imports()
    docker_ok = test_docker_imports()
    
    if local_ok and docker_ok:
        print("\n✓ Todas las pruebas pasaron correctamente")
    else:
        print("\n✗ Algunas pruebas fallaron")
        sys.exit(1) 