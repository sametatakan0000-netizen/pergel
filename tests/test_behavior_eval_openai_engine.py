"""behavior_eval_run OpenAI-uyumlu sunucu motoru TDD testleri.

Stub HTTP sunucu (http.server, iş parçacığında) kullanılır — gerçek ağ yok.
unittest tabanlı (repo standardı; pytest kurulu değil).
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import behavior_eval_run as ber  # noqa: E402


def aciklama(metin: str) -> str:
    """OpenAI /chat/completions yanıt gövdesi (choices[0].message.content)."""
    return json.dumps({"choices": [{"message": {"content": metin}}]})


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # sessiz
        pass

    def do_POST(self):
        uzunluk = int(self.headers.get("Content-Length", 0))
        govde = self.rfile.read(uzunluk)
        self.server.alinanlar.append({"path": self.path, "body": json.loads(govde)})
        durum, metin = self.server.yanitlar.pop(0) if self.server.yanitlar else (200, "{}")
        bayt = metin.encode("utf-8")
        self.send_response(durum)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(bayt)))
        self.end_headers()
        self.wfile.write(bayt)


def sunucu_baslat(yanitlar: list[tuple[int, str]]):
    sunucu = HTTPServer(("127.0.0.1", 0), StubHandler)
    sunucu.yanitlar = list(yanitlar)
    sunucu.alinanlar = []
    is_parcacigi = threading.Thread(target=sunucu.serve_forever, daemon=True)
    is_parcacigi.start()
    taban = f"http://127.0.0.1:{sunucu.server_address[1]}/v1"
    return sunucu, taban


def bos_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestOpenAIEngineGenerate(unittest.TestCase):
    """OpenAIEngine.generate: istek şekli, yanıt ayrıştırma, sıralama, hata/tekrar."""

    def setUp(self):
        self._eski_bekleme = ber.OpenAIEngine.BEKLEME
        ber.OpenAIEngine.BEKLEME = 0  # testlerde geri çekilme uyumasın

    def tearDown(self):
        ber.OpenAIEngine.BEKLEME = self._eski_bekleme
        if getattr(self, "sunucu", None) is not None:
            self.sunucu.shutdown()
            self.sunucu.server_close()

    def _baslat(self, yanitlar):
        self.sunucu, self.taban = sunucu_baslat(yanitlar)
        return ber.OpenAIEngine(self.taban, "test-model", 16)

    def test_istek_sekli(self):
        motor = self._baslat([(200, aciklama("cevap"))])
        sonuc = motor.generate(["merhaba"])
        self.assertEqual(sonuc, ["cevap"])
        self.assertEqual(len(self.sunucu.alinanlar), 1)
        kayit = self.sunucu.alinanlar[0]
        self.assertEqual(kayit["path"], "/v1/chat/completions")
        govde = kayit["body"]
        self.assertEqual(govde["model"], "test-model")
        self.assertEqual(govde["messages"], [{"role": "user", "content": "merhaba"}])
        self.assertEqual(govde["max_tokens"], 16)
        self.assertEqual(govde["temperature"], 0)
        self.assertEqual(govde["top_p"], 1)

    def test_yanit_ayristirma_ve_sira_korunur(self):
        motor = self._baslat([
            (200, aciklama("A")),
            (200, aciklama("B")),
            (200, aciklama("C")),
        ])
        sonuc = motor.generate(["bir", "iki", "uc"])
        self.assertEqual(sonuc, ["A", "B", "C"])
        self.assertEqual(
            [k["body"]["messages"][0]["content"] for k in self.sunucu.alinanlar],
            ["bir", "iki", "uc"],
        )

    def test_500_tekrarlardan_sonra_runtime_error(self):
        motor = self._baslat([(500, "sunucu hatasi")] * 3)
        with self.assertRaises(RuntimeError) as ba:
            motor.generate(["x"])
        metin = str(ba.exception)
        self.assertIn("500", metin)
        self.assertIn("sunucu hatasi", metin)
        self.assertEqual(len(self.sunucu.alinanlar), 3)  # 3 deneme

    def test_5xx_tekrar_sonrasi_basari(self):
        motor = self._baslat([(500, "gecici"), (200, aciklama("tamam"))])
        sonuc = motor.generate(["x"])
        self.assertEqual(sonuc, ["tamam"])
        self.assertEqual(len(self.sunucu.alinanlar), 2)  # 1 hata + 1 başarı

    def test_4xx_tekrar_yok(self):
        motor = self._baslat([(400, "kotu istek")])
        with self.assertRaises(RuntimeError) as ba:
            motor.generate(["x"])
        metin = str(ba.exception)
        self.assertIn("400", metin)
        self.assertIn("kotu istek", metin)
        self.assertEqual(len(self.sunucu.alinanlar), 1)  # tekrar yok

    def test_baglanti_hatasi_tekrar_sonra_runtime_error(self):
        motor = ber.OpenAIEngine(f"http://127.0.0.1:{bos_port()}/v1", "test-model", 16)
        with mock.patch.object(ber.time, "sleep") as uyku:
            with self.assertRaises(RuntimeError):
                motor.generate(["x"])
        self.assertEqual(uyku.call_count, 2)  # 3 deneme arası 2 geri çekilme


class TestArgumanDogrulama(unittest.TestCase):
    """CLI doğrulaması: --taban-url / --model-dir / --repo kombinasyon kuralları."""

    def _dogrula(self, *argv):
        args = ber.arguman_parser().parse_args(list(argv))
        ber.argumanlar_dogrula(args)
        return args

    def test_taban_url_motor_ad_zorunlu(self):
        with self.assertRaises(ValueError) as ba:
            self._dogrula("--taban-url", "http://127.0.0.1:8001/v1", "--davranis", "dil_karar")
        self.assertIn("--motor-ad", str(ba.exception))

    def test_taban_url_ile_model_dir_verilemez(self):
        with self.assertRaises(ValueError) as ba:
            self._dogrula(
                "--taban-url", "http://127.0.0.1:8001/v1", "--motor-ad", "m",
                "--model-dir", "/mnt/x", "--davranis", "dil_karar",
            )
        self.assertIn("--model-dir", str(ba.exception))

    def test_taban_url_tamam(self):
        args = self._dogrula(
            "--taban-url", "http://127.0.0.1:8001/v1", "--motor-ad", "m",
            "--davranis", "dil_karar",
        )
        self.assertEqual(args.taban_url, "http://127.0.0.1:8001/v1")

    def test_hf_yolu_model_dir_zorunlu(self):
        with self.assertRaises(ValueError) as ba:
            self._dogrula("--repo", "Qwen/Qwen3-8B", "--davranis", "guvenlik")
        self.assertIn("--model-dir", str(ba.exception))

    def test_hf_yolu_repo_zorunlu(self):
        with self.assertRaises(ValueError) as ba:
            self._dogrula("--model-dir", "/mnt/x", "--davranis", "guvenlik")
        self.assertIn("--repo", str(ba.exception))

    def test_hf_yolu_tamam(self):
        args = self._dogrula(
            "--model-dir", "/mnt/x", "--repo", "Qwen/Qwen3-8B", "--davranis", "guvenlik",
        )
        self.assertEqual(args.model_dir, "/mnt/x")


class TestRunId(unittest.TestCase):
    """Sunucu yolunda run_id HF koşularıyla çakışmamalı (_openai ekli)."""

    def _args(self, **kw):
        temel = dict(model_dir=None, repo=None, motor_ad=None, taban_url=None,
                     davranis="dil_karar")
        temel.update(kw)
        return type("Args", (), temel)()

    def test_sunucu_yolu_run_id_openai_ekli(self):
        args = self._args(taban_url="http://127.0.0.1:8001/v1", motor_ad="qwen3-8b")
        self.assertEqual(ber.run_id_hesapla(args), "qwen3-8b_dil_karar_openai")

    def test_hf_yolu_run_id_degismez(self):
        args = self._args(model_dir="/mnt/x", repo="Qwen/Qwen3-8B")
        self.assertEqual(ber.run_id_hesapla(args), "Qwen_Qwen3-8B_dil_karar")

    def test_run_id_temizleme(self):
        args = self._args(taban_url="http://127.0.0.1:8001/v1", motor_ad="org/model:x")
        self.assertEqual(ber.run_id_hesapla(args), "org_model_x_dil_karar_openai")


if __name__ == "__main__":
    unittest.main()
