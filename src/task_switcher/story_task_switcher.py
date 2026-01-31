#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Gemini
# @Date:   2026-01-30 14:44:48
# @Last Modified by:   Andreas Paepcke
# @Last Modified time: 2026-01-31 12:00:30

from flask import Flask, render_template_string, jsonify
import subprocess
import socket


class AIServiceController:
    """
    Flask-based web controller for managing AI services (ComfyUI, TabbyAPI, SillyTavern).
    Provides a web interface to switch between art generation and story writing modes.
    """
    SERVER_IP = '192.168.1.111'
    
    # HTML template for the web interface
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AI Control Center</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; text-align: center; padding: 50px; background: #121212; color: white; }
        .control-group { display: flex; align-items: center; justify-content: center; margin: 20px auto; width: 350px; }
        .btn { flex-grow: 1; padding: 20px; font-size: 18px; cursor: pointer; border-radius: 10px; border: none; text-decoration: none; color: white; transition: 0.2s; }
        .art { background: #6200ea; }
        .story { background: #03dac6; color: black; }
        
        /* LED Styling */
        .led { width: 15px; height: 15px; border-radius: 50%; margin-left: 15px; background-color: #333; box-shadow: inset 0 0 5px #000; transition: 0.3s; }
        .led-on { background-color: #39FF14; box-shadow: 0 0 10px #39FF14, 0 0 20px #39FF14; }
        
        h1 { margin-bottom: 40px; font-weight: 300; }
        
        /* Loading overlay */
        #loading-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
            flex-direction: column;
        }
        #loading-overlay.active { display: flex; }
        .spinner {
            border: 4px solid #333;
            border-top: 4px solid #39FF14;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin-bottom: 20px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        #loading-text { font-size: 18px; color: #39FF14; }
    </style>
    <script>
        async function switchAndOpen(mode, url, port, tabName, serviceName) {
            // Show loading overlay
            const overlay = document.getElementById('loading-overlay');
            const loadingText = document.getElementById('loading-text');
            overlay.className = 'active';
            loadingText.textContent = `Starting ${serviceName}...`;
            
            try {
                // Trigger the service switch first
                await fetch(`/focus/${mode}`);
                
                // Map mode to service name for checking
                const serviceCheckName = mode === 'art' ? 'comfy' : 'silly';
                
                // Poll until service is ready (max 60 seconds)
                const maxAttempts = 120;
                let serviceReady = false;
                
                for (let i = 0; i < maxAttempts; i++) {
                    try {
                        const response = await fetch(`/check_ready/${serviceCheckName}`);
                        const data = await response.json();
                        
                        if (data.ready) {
                            serviceReady = true;
                            loadingText.textContent = `${serviceName} ready! Opening...`;
                            await new Promise(r => setTimeout(r, 500));
                            break;
                        }
                    } catch (e) {
                        // Continue waiting
                    }
                    
                    // Update progress
                    const dots = '.'.repeat((i % 3) + 1);
                    const elapsed = Math.floor(i / 2);
                    loadingText.textContent = `Waiting for ${serviceName}${dots} (${elapsed}s)`;
                    await new Promise(r => setTimeout(r, 500));
                }
                
                if (!serviceReady) {
                    loadingText.textContent = `Opening ${serviceName}...`;
                    await new Promise(r => setTimeout(r, 500));
                }
                
                // Open the tab
                const newTab = window.open(url, tabName);
                
                // Immediately switch back to this tab
                window.focus();
                
            } catch (error) {
                loadingText.textContent = 'Error: ' + error.message;
                await new Promise(r => setTimeout(r, 2000));
            } finally {
                overlay.className = '';
            }
        }
        
        async function updateStatus() {
            const response = await fetch('/status');
            const data = await response.json();
            
            document.getElementById('led-comfy').className = data.comfy ? 'led led-on' : 'led';
            document.getElementById('led-tabby').className = data.tabby ? 'led led-on' : 'led';
        }
        
        // Poll every 2 seconds
        setInterval(updateStatus, 2000);
        window.onload = updateStatus;
    </script>
</head>
<body>
    <div id="loading-overlay">
        <div class="spinner"></div>
        <div id="loading-text">Starting service...</div>
    </div>
    
    <h1>AI Workstation: {{ machine_name }}</h1>
    
    <div class="control-group">
        <a href="#" onclick="switchAndOpen('art', '{{ comfy_url }}', {{ comfy_port }}, 'ComfyUITab', 'ComfyUI'); return false;" class="btn art">🎨 Focus on Art</a>
        <div id="led-comfy" class="led"></div>
    </div>
    <div class="control-group">
        <a href="#" onclick="switchAndOpen('story', '{{ st_url }}', {{ st_port }}, 'SillyTavernTab', 'SillyTavern'); return false;" class="btn story">📖 Focus on Story</a>
        <div id="led-tabby" class="led"></div>
    </div>
</body>
</html>
"""
    
    def __init__(self, 
                 server_ip: str = '192.168.1.111',
                 comfy_port: int = 8188,
                 silly_tavern_port: int = 8000,
                 machine_name: str = 'SEXTUS',
                 flask_port: int = 5050):
        """
        Initialize the AI Service Controller.
        
        Args:
            server_ip: IP address of the server hosting the services
            comfy_port: Port for ComfyUI service
            silly_tavern_port: Port for SillyTavern service
            machine_name: Display name for the workstation
            flask_port: Port for this Flask control server
        """
        self.server_ip = server_ip
        self.comfy_port = comfy_port
        self.silly_tavern_port = silly_tavern_port
        self.machine_name = machine_name
        self.flask_port = flask_port
        
        # Service configuration
        self.services = {
            'comfy': 'comfyui',
            'tabby': 'tabbyapi',
            'silly': 'silly-tavern'
        }
        
        # Build URLs
        self.comfy_url = f"http://{self.server_ip}:{self.comfy_port}"
        self.st_url = f"http://{self.server_ip}:{self.silly_tavern_port}"
        
        # Initialize Flask app
        self.app = Flask(__name__)
        self._register_routes()
        
        # Ensure that the Silly Tavern Web UI is running on the server
        self._start_service(self.services['silly'])
    
    def _is_service_active(self, service_name: str) -> bool:
        """
        Check if a systemctl service is active.
        
        Args:
            service_name: Name of the systemd service
            
        Returns:
            True if service is active, False otherwise
        """
        result = subprocess.call(
            ["systemctl", "is-active", "--quiet", service_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result == 0
    
    def _is_port_ready(self, port: int) -> bool:
        """
        Check if a port is accepting connections.
        
        Args:
            port: Port number to check
            
        Returns:
            True if port is accepting connections, False otherwise
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)  # Increased timeout
            result = sock.connect_ex(('127.0.0.1', port))  # Check localhost, not remote IP
            sock.close()
            return result == 0
        except Exception as e:
            print(f"Port check error for {port}: {e}")
            return False
    
    def _stop_service(self, service_name: str) -> bool:
        """
        Stop a systemctl service.
        
        Args:
            service_name: Name of the systemd service
            
        Returns:
            True if successful, False otherwise
        """
        result = subprocess.run(
            ["/usr/bin/sudo", "/usr/bin/systemctl", "stop", service_name],
            capture_output=True
        )
        return result.returncode == 0
    
    def _start_service(self, service_name: str) -> bool:
        """
        Start a systemctl service.
        
        Args:
            service_name: Name of the systemd service
            
        Returns:
            True if successful, False otherwise
        """
        result = subprocess.run(
            ["/usr/bin/sudo", "/usr/bin/systemctl", "start", service_name],
            capture_output=True
        )
        return result.returncode == 0
    
    def _switch_to_art_mode(self) -> None:
        """Switch to art generation mode (ComfyUI active, TabbyAPI stopped)."""
        self._stop_service(self.services['tabby'])
        self._start_service(self.services['comfy'])
    
    def _switch_to_story_mode(self) -> None:
        """Switch to story writing mode (TabbyAPI active, ComfyUI stopped)."""
        self._stop_service(self.services['comfy'])
        self._start_service(self.services['tabby'])
        self._start_service(self.services['silly'])
    
    def _register_routes(self) -> None:
        """Register Flask routes."""
        
        @self.app.route('/')
        def index():
            return render_template_string(
                self.HTML_TEMPLATE,
                comfy_url=self.comfy_url,
                st_url=self.st_url,
                comfy_port=self.comfy_port,
                st_port=self.silly_tavern_port,
                server_ip=self.server_ip,
                machine_name=self.machine_name
            )
        
        @self.app.route('/status')
        def get_status():
            return jsonify({
                "comfy": self._is_service_active(self.services['comfy']),
                "tabby": self._is_service_active(self.services['tabby'])
            })
        
        @self.app.route('/check_ready/<service>')
        def check_ready(service):
            """Check if a service port is accepting connections"""
            port_map = {
                'comfy': self.comfy_port,
                'silly': self.silly_tavern_port
            }
            
            if service not in port_map:
                return jsonify({"ready": False})
            
            port = port_map[service]
            is_ready = self._is_port_ready(port)
            print(f"Checking {service} on port {port}: {is_ready}")  # Debug logging
            return jsonify({"ready": is_ready})
        
        @self.app.route('/focus/<mode>')
        def switch_mode(mode):
            if mode == "art":
                self._switch_to_art_mode()
            elif mode == "story":
                self._switch_to_story_mode()
            return '', 204
    
    def run(self, host: str = '0.0.0.0', debug: bool = False, use_production_server: bool = False) -> None:
        """
        Start the Flask server.
        
        Args:
            host: Host address to bind to
            debug: Enable Flask debug mode
            use_production_server: Use waitress production server instead of Flask dev server
        """
        if use_production_server:
            try:
                from waitress import serve
                print(f"Starting production server on {host}:{self.flask_port}")
                serve(self.app, host=host, port=self.flask_port)
            except ImportError:
                print("WARNING: waitress not installed. Install with: pip install waitress")
                print("Falling back to Flask development server...")
                self.app.run(host=host, port=self.flask_port, debug=debug)
        else:
            self.app.run(host=host, port=self.flask_port, debug=debug)


if __name__ == '__main__':
    controller = AIServiceController(
        server_ip=AIServiceController.SERVER_IP,
        comfy_port=8188,
        silly_tavern_port=8000,
        machine_name='SEXTUS',
        flask_port=5050
    )
    controller.run(use_production_server=True)
    