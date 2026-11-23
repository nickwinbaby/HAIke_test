import unittest

from core.aes_crypto import aes_decrypt, aes_encrypt


class AesCryptoTests(unittest.TestCase):
    def test_cbc_pkcs7_base64_round_trip(self):
        options = dict(
            mode="CBC",
            padding="PKCS7",
            key_bits=128,
            key_format="Text",
            iv="1234567890ABCDEF",
            iv_format="Text",
            encoding="UTF-8",
        )
        encrypted = aes_encrypt(
            "中国abc", "1234567890ABCDEF", output_format="Base64", **options
        )
        self.assertEqual(
            aes_decrypt(
                encrypted,
                "1234567890ABCDEF",
                input_format="Base64",
                **options,
            ),
            "中国abc",
        )

    def test_ecb_known_vector_without_padding(self):
        encrypted = aes_encrypt(
            "00112233445566778899AABBCCDDEEFF",
            "000102030405060708090A0B0C0D0E0F",
            mode="ECB",
            padding="None",
            key_bits=128,
            key_format="Hex",
            encoding="Hex",
            output_format="Hex",
        )
        self.assertEqual(encrypted, "69C4E0D86A7B0430D8CDB78070B4C55A")

    def test_hex_plaintext_and_key_validation(self):
        with self.assertRaises(ValueError):
            aes_encrypt("00", "short", mode="ECB", key_bits=128, padding="PKCS7")
        with self.assertRaises(ValueError):
            aes_decrypt(
                "not-base64",
                "1234567890ABCDEF",
                mode="ECB",
                input_format="Base64",
            )


if __name__ == "__main__":
    unittest.main()
