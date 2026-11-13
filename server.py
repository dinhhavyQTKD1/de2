"""
Localhost Web Server for Nam Việt AI Agent
Provides REST API & Full Interactive Web UI on http://localhost:8000
Zero external dependencies - built on Python 3 standard library
"""
import sys
import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket

from config.settings import BASE_DIR, DATA_DIR, OUTPUTS_DIR, load_rules
from agent.orchestrator import NamVietAgentOrchestrator
from web.generate_dashboard import generate_dashboard

PORT = 8000

def load_file(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default if default is not None else {}
    return default if default is not None else {}

class NamVietAPIHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content, status_code=200):
        body = html_content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ["/", "/index.html", "/dashboard"]:
            dashboard_file = os.path.join(BASE_DIR, "web", "dashboard.html")
            if not os.path.exists(dashboard_file):
                generate_dashboard()
            with open(dashboard_file, "r", encoding="utf-8") as f:
                content = f.read()
            self._send_html(content)

        elif path in ["/presentation", "/slides", "/slide"]:
            presentation_file = os.path.join(BASE_DIR, "web", "presentation.html")
            with open(presentation_file, "r", encoding="utf-8") as f:
                content = f.read()
            self._send_html(content)

        elif path == "/favicon.ico":
            svg_icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="50" fill="#f472b6"/><text y=".9em" x="20" font-size="70">🌸</text></svg>'.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(svg_icon)))
            self.end_headers()
            self.wfile.write(svg_icon)

        elif path == "/api/status":
            summary = load_file(os.path.join(OUTPUTS_DIR, "summary_report.json"), {})
            self._send_json({
                "status": "ONLINE",
                "service": "NamViet AI Lead Dispatcher Localhost",
                "version": "2.0.0",
                "port": PORT,
                "summary": summary
            })

        elif path == "/api/summary":
            self._send_json(load_file(os.path.join(OUTPUTS_DIR, "summary_report.json"), {}))

        elif path == "/api/customers":
            self._send_json(load_file(os.path.join(OUTPUTS_DIR, "master_customers.json"), []))

        elif path == "/api/tasks":
            self._send_json(load_file(os.path.join(OUTPUTS_DIR, "sales_task_assignments.json"), {}))

        elif path == "/api/escalations":
            self._send_json(load_file(os.path.join(OUTPUTS_DIR, "manager_escalations.json"), []))

        elif path == "/api/dnc":
            self._send_json(load_file(os.path.join(OUTPUTS_DIR, "do_not_contact.json"), []))

        elif path == "/api/audit":
            self._send_json(load_file(os.path.join(OUTPUTS_DIR, "execution_log.json"), {}))

        else:
            self.send_error(404, "Endpoint Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            payload = {}

        if path == "/api/run":
            # Select target dataset
            dataset_type = payload.get("dataset", "standard") # 'standard', '700_benchmark', or 'uploaded'
            if dataset_type == "700_benchmark":
                target_file = os.path.join(DATA_DIR, "leads_700_benchmark.json")
            elif dataset_type == "uploaded":
                target_file = os.path.join(DATA_DIR, "uploaded_leads.json")
            else:
                target_file = os.path.join(DATA_DIR, "leads_input.json")

            if not os.path.exists(target_file):
                self._send_json({"error": f"Dataset file {target_file} not found"}, 400)
                return

            orchestrator = NamVietAgentOrchestrator(leads_file=target_file)
            results = orchestrator.execute_pipeline()
            generate_dashboard()

            self._send_json({
                "success": True,
                "message": f"AI Agent executed successfully with dataset '{dataset_type}'",
                "summary": results["summary"]
            })

        elif path == "/api/upload":
            # Upload new leads array from frontend
            leads_data = payload.get("leads", [])
            if not isinstance(leads_data, list) or len(leads_data) == 0:
                self._send_json({"error": "Payload must contain a non-empty 'leads' array"}, 400)
                return

            upload_file = os.path.join(DATA_DIR, "uploaded_leads.json")
            with open(upload_file, "w", encoding="utf-8") as f:
                json.dump(leads_data, f, ensure_ascii=False, indent=2)

            orchestrator = NamVietAgentOrchestrator(leads_file=upload_file)
            results = orchestrator.execute_pipeline()
            generate_dashboard()

            self._send_json({
                "success": True,
                "message": f"Uploaded {len(leads_data)} leads and executed AI Agent pipeline successfully!",
                "summary": results["summary"]
            })

        elif path == "/api/approve-escalation":
            cust_id = payload.get("customer_id")
            chosen_rep = payload.get("rep_name", "Nguyễn Văn An")
            action_notes = payload.get("notes", "Đã được Trưởng phòng phê duyệt chỉ định")

            escalations_file = os.path.join(OUTPUTS_DIR, "manager_escalations.json")
            escalations = load_file(escalations_file, [])
            updated = [e for e in escalations if e.get("customer_id") != cust_id]

            with open(escalations_file, "w", encoding="utf-8") as f:
                json.dump(updated, f, ensure_ascii=False, indent=2)

            generate_dashboard()
            self._send_json({
                "success": True,
                "customer_id": cust_id,
                "assigned_to": chosen_rep,
                "remaining_escalations": len(updated)
            })

        else:
            self.send_error(404, "Endpoint Not Found")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def run_server():
    global PORT
    # Allow custom port from CLI: python server.py 8080 or python server.py --port 8080
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        PORT = int(sys.argv[1])
    elif "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            PORT = int(sys.argv[idx + 1])
    elif is_port_in_use(PORT):
        PORT = 8080
    if is_port_in_use(PORT):
        PORT = 8888

    server_address = ("127.0.0.1", PORT)
    httpd = HTTPServer(server_address, NamVietAPIHandler)

    print("=" * 80)
    print("      CÔNG TY CỔ PHẦN PHẦN MỀM NAM VIỆT - AI AGENT LOCALHOST SERVER")
    print("=" * 80)
    print(f"[+] Server dang chay tai dia chi: http://localhost:{PORT}")
    print(f"[+] Mo trinh duyet (Chrome/Edge/Firefox) va truy cap: http://localhost:{PORT}")
    print(f"[+] REST APIs san sang:")
    print(f"    - GET  /api/status        : Kiem tra trang thai server")
    print(f"    - GET  /api/summary       : Xem bao cao tong hop")
    print(f"    - GET  /api/customers     : Danh sach Master Customers")
    print(f"    - GET  /api/tasks         : Danh sach cong viec 8 NVKD")
    print(f"    - GET  /api/escalations   : Danh sach can Truong phong duyet")
    print(f"    - GET  /api/dnc           : Danh sach chan lien he (DNC)")
    print(f"    - GET  /api/audit         : Nhat ky truy vet kiem toan")
    print(f"    - POST /api/run           : Kich hoat chay Agent truc tiep")
    print(f"    - POST /api/upload        : Nap bo du lieu moi tu UI")
    print("-" * 80)
    print("[*] Nhan Ctrl+C de dung server khi hoan tat.")
    print("=" * 80)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Dung server localhost.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()

