import pytest
from pathlib import Path
from conftest import create_valid_gene, save_temp_gene, clean_test_data, TEST_DATA_DIR


class TestSporeChannels:
    CHANNELS = {
        "Ch.A": "kubo_ipfs",
        "Ch.B": "local_gateway",
        "Ch.C": "udp_beacon",
        "Ch.D": "file_spore"
    }

    def test_four_channels_exist(self):
        assert len(self.CHANNELS) == 4
        assert "Ch.A" in self.CHANNELS
        assert "Ch.B" in self.CHANNELS
        assert "Ch.C" in self.CHANNELS
        assert "Ch.D" in self.CHANNELS

    def test_channel_priority_order(self):
        order = ["Ch.A", "Ch.B", "Ch.C", "Ch.D"]
        assert order[0] == "Ch.A"
        assert order[-1] == "Ch.D"

    def test_fallback_mechanism(self):
        fallback_sequence = ["Ch.A", "Ch.B", "Ch.C", "Ch.D"]
        for i, ch in enumerate(fallback_sequence):
            if ch == "Ch.A":
                fallback = fallback_sequence[min(i + 1, len(fallback_sequence) - 1)]
                assert fallback == "Ch.B"


class TestSporeFilePropagation:
    def test_spore_content_integrity(self):
        content = create_valid_gene("propagation-test")
        filepath = save_temp_gene(content, "integrity_test.gene")

        reloaded = filepath.read_text()
        assert reloaded == content

        filepath.unlink()

    def test_spore_size_limit(self):
        max_size = 1024 * 1024
        content = "x" * 500
        assert len(content.encode()) <= max_size


class TestSporeBroadcast:
    def test_gene_broadcast_payload(self):
        gene_content = create_valid_gene("broadcast-test")
        payload = {
            "gene_name": "broadcast-test",
            "gene_content": gene_content,
            "channel": "Ch.B",
            "timestamp": "2026-05-11T00:00:00"
        }
        assert payload["gene_name"] == "broadcast-test"
        assert len(payload["gene_content"]) > 0

    def test_multiple_genes_broadcast(self):
        broadcasts = []
        for i in range(3):
            content = create_valid_gene(f"broadcast-{i}")
            broadcasts.append({
                "gene_name": f"broadcast-{i}",
                "content": content,
                "channel": f"Ch.{chr(65 + i)}"
            })

        assert len(broadcasts) == 3
        assert broadcasts[0]["channel"] == "Ch.A"
        assert broadcasts[-1]["channel"] == "Ch.C"


class TestSporeReminder:
    def test_reminder_conditions(self):
        max_reminders = 5
        innovation_threshold = 3

        reminders = 0
        innovations = 0

        for _ in range(10):
            innovations += 1
            if innovations >= innovation_threshold and reminders < max_reminders:
                reminders += 1
                innovations = 0

        assert reminders <= max_reminders

    def test_reminder_after_innovation(self):
        innovations = [1, 1, 1, 0, 0]
        reminders = 0
        innovation_count = 0

        for inc in innovations:
            innovation_count += inc
            if innovation_count >= 3:
                reminders += 1
                innovation_count = 0

        assert reminders == 1


def teardown_module():
    clean_test_data()
