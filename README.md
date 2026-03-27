# 20-20-20 Eye Monitor 👀

Un servicio reactivo y ligero en Python para Windows que te ayuda a prevenir la fatiga visual aplicando la regla del 20-20-20 (cada 20 minutos, mirar a 20 pies/6 metros durante 20 segundos).

## 🚀 Características
* **Reactivo:** Usa la API de Windows (`Win32 Hooks`) para pausar el temporizador si suspendes la laptop o bloqueas la sesión. Solo cuenta el tiempo real de uso.
* **Silencioso:** Se ejecuta en segundo plano como un proceso `.pyw` (cero ventanas molestas, cero consumo excesivo de CPU gracias a Windows Message Pump).
* **Multimodal:** Alerta visual nativa de escritorio y alerta de voz (TTS) para asegurar que no te saltes el descanso.

## ⚙️ Requisitos
* Windows 10/11
* Python 3.x

## 🛠️ Instalación y Uso
1. Clona este repositorio: `git clone https://github.com/tu-usuario/20-20-20-eye-monitor.git`
2. Crea un entorno virtual: `python -m venv .venv`
3. Activa el entorno e instala las dependencias: `pip install -r requirements.txt`
4. Ejecuta el script o usa el archivo `.bat` provisto para añadirlo al inicio automático de Windows.