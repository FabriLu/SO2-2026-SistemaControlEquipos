# Sistema de Control, Monitoreo y Recuperación de Equipos Informáticos

Proyecto de semestre orientado al desarrollo de un sistema centralizado para la administración de equipos informáticos en aulas de laboratorio.

El sistema permitirá que un equipo central, utilizado por el docente o administrador, pueda supervisar el estado de las computadoras conectadas a la red, consultar el uso de sus recursos y ejecutar acciones de administración autorizadas de forma remota.

## Funcionalidades

- Registro y gestión de equipos del laboratorio.
- Monitoreo del uso de CPU, memoria RAM y almacenamiento.
- Visualización del estado y disponibilidad de los equipos.
- Envío de mensajes a las computadoras conectadas.
- Bloqueo y desbloqueo de equipos.
- Reinicio y apagado remoto.
- Registro de eventos y acciones realizadas.
- Generación de alertas ante determinados eventos.
- Recuperación de los equipos a un estado funcional previamente establecido.

## Tecnologías

- **Python** y **Flask** — Servidor y API REST.
- **SQLite** — Base de datos local para inventario, credenciales y auditoría de eventos.
- **HTML5, Vanilla CSS (Glassmorphism Dark) y JavaScript** — Panel de control docente en vivo.
- **Proxmox VE REST API** — Mecanismo de recuperación de máquinas virtuales mediante rollback al snapshot `estado_limpio`.
- **psutil** — Monitoreo de recursos de hardware (CPU, RAM y almacenamiento).
- **Tkinter & Subprocess** — Bloqueo de pantalla y notificaciones en clientes Ubuntu.
- **Ubuntu Server 24.04** — Servidor central del docente.
- **Ubuntu Desktop 24.04** — Equipos cliente de los estudiantes.
- **Systemd** — Servicio en segundo plano para el agente.
- **Git y GitHub** — Control de versiones.

## Entorno de pruebas

El proyecto será desarrollado y probado inicialmente en un entorno virtualizado mediante **Proxmox VE**, simulando una red de laboratorio con un servidor central y múltiples equipos cliente.

Esto permitirá evaluar la comunicación, monitoreo y administración remota de los equipos antes de realizar pruebas en un entorno físico.

## Estado del proyecto

> 🚧 **En desarrollo**

Nombre: Fabrizio Hernán

Apellido: Magne Luizaga

Grupo:

Rol o responsabilidad principal: Scrum master, Desarrollador
