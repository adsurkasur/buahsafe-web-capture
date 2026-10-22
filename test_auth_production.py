from __future__ import annotations

# Arahkan ke DB sementara SEBELUM import database/app: suite ini tidak boleh
# menulis ke data/buahsafe.db (dataset pengukuran nyata).
import os
import tempfile
os.environ.setdefault("BUAHSAFE_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="buahsafe-test-"), "test.db"))

import secrets
import unittest
from flask.testing import FlaskClient

import database
from app import app


class TestAuthProduction(unittest.TestCase):
    def setUp(self):
        database.initialize()
        self.client: FlaskClient = app.test_client()

    def test_00_isolated_database(self):
        real_db = database.ROOT / "data" / "buahsafe.db"
        self.assertNotEqual(database.DATABASE_PATH.resolve(), real_db.resolve())

    def test_01_password_hashing(self):
        salt, h = database.hash_password("operator123")
        self.assertTrue(database.verify_password("operator123", salt, h))
        self.assertFalse(database.verify_password("wrong_password", salt, h))

    def test_02_login_success(self):
        res = self.client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "operator")
        self.assertEqual(data["user"]["username"], "operator")

    def test_03_login_failure_wrong_password(self):
        res = self.client.post("/api/auth/login", json={"username": "operator", "password": "salah_password"})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data.get("ok"))

    def test_04_protected_route_without_token(self):
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 401)

        res_users = self.client.get("/api/users")
        self.assertEqual(res_users.status_code, 401)

    def test_05_protected_route_with_invalid_token(self):
        headers = {"Authorization": "Bearer invalid_token_12345"}
        res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(res.status_code, 401)

    def test_06_rbac_operator_forbidden_owner_routes(self):
        # Login sebagai operator
        res = self.client.post("/api/auth/login", json={"username": "operator", "password": "operator123"})
        op_token = res.get_json()["token"]
        headers = {"Authorization": f"Bearer {op_token}"}

        # Operator bisa akses me
        res_me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(res_me.status_code, 200)

        # Operator TIDAK BISA akses /api/users
        res_users = self.client.get("/api/users", headers=headers)
        self.assertEqual(res_users.status_code, 403)

        # Operator TIDAK BISA buat petani
        res_petani = self.client.post("/api/master-data/petani", headers=headers, json={"name": "Budi"})
        self.assertEqual(res_petani.status_code, 403)

    def test_07_owner_user_management_lifecycle(self):
        # Login sebagai owner
        res_login = self.client.post("/api/auth/login", json={"username": "owner", "password": "owner123"})
        self.assertEqual(res_login.status_code, 200)
        owner_token = res_login.get_json()["token"]
        owner_headers = {"Authorization": f"Bearer {owner_token}"}

        # 1. List users
        res_list = self.client.get("/api/users", headers=owner_headers)
        self.assertEqual(res_list.status_code, 200)
        users = res_list.get_json()["users"]
        self.assertGreaterEqual(len(users), 3)

        # 2. Create new user
        test_user = f"qc_{secrets.token_hex(4)}"
        res_create = self.client.post(
            "/api/users",
            headers=owner_headers,
            json={
                "username": test_user,
                "name": "Staff QC Uji Coba",
                "password": "passwordBaru123",
                "role": "supervisor",
            },
        )
        self.assertEqual(res_create.status_code, 201)
        created_user = res_create.get_json()["user"]
        created_id = created_user["id"]

        # 3. New user login
        res_new_login = self.client.post(
            "/api/auth/login",
            json={"username": test_user, "password": "passwordBaru123"},
        )
        self.assertEqual(res_new_login.status_code, 200)
        new_token = res_new_login.get_json()["token"]

        # 4. Update password
        res_pw = self.client.put(
            f"/api/users/{created_id}/password",
            headers=owner_headers,
            json={"password": "passwordGanti456"},
        )
        self.assertEqual(res_pw.status_code, 200)

        # Token lama langsung tidak berlaku karena password diubah
        res_old_token = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        self.assertEqual(res_old_token.status_code, 401)

        # Login dengan password baru
        res_relogin = self.client.post(
            "/api/auth/login",
            json={"username": test_user, "password": "passwordGanti456"},
        )
        self.assertEqual(res_relogin.status_code, 200)
        valid_new_token = res_relogin.get_json()["token"]

        # 5. Delete (soft delete / deactivate) user
        res_del = self.client.delete(f"/api/users/{created_id}", headers=owner_headers)
        self.assertEqual(res_del.status_code, 200)

        # Token yang aktif langsung hangus
        res_revoked = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {valid_new_token}"})
        self.assertEqual(res_revoked.status_code, 401)

        # Pengguna nonaktif tidak bisa login lagi
        res_inactive_login = self.client.post(
            "/api/auth/login",
            json={"username": test_user, "password": "passwordGanti456"},
        )
        self.assertEqual(res_inactive_login.status_code, 401)

    def test_08_logout_revokes_token(self):
        res = self.client.post("/api/auth/login", json={"username": "supervisor", "password": "spv123"})
        token = res.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Sebelum logout: valid
        res_me = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(res_me.status_code, 200)

        # Logout
        res_logout = self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(res_logout.status_code, 200)

        # Setelah logout: token hangus
        res_after = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(res_after.status_code, 401)


if __name__ == "__main__":
    unittest.main()
