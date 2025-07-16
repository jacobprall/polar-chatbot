```polar
actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };

  "read" if "admin";
  "write" if "admin";
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = {
    creator: User,
    organization: Organization
  };

  "edit" if "editor";
  "read" if "reader" and not is_private(resource);
}

allow(user: User, action: String, doc: Documents) if
  org matches Organization and
  has_relation(doc, "organization", org) and
  has_role(user, "admin", org);

allow(user: User, action: String, doc: Documents) if
  has_role(user, "reader", doc) or
  has_role(user, "editor", doc);
```

Test cases to confirm the Polar rules implements the required logic.

```polar
test "Admins can read and edit documents under their organization" {
  setup {
    has_role(User{"admin_user"}, "admin", Organization{"org_1"});
    has_relation(Documents{"doc_1"}, "organization", Organization{"org_1"});
  }

  assert allow(User{"admin_user"}, "read", Documents{"doc_1"});
  assert allow(User{"admin_user"}, "edit", Documents{"doc_1"});
}

test "Members cannot read private documents" {
  setup {
    has_role(User{"member_user"}, "member", Organization{"org_2"});
    has_relation(Documents{"private_doc"}, "organization", Organization{"org_2"});
    is_private(Documents{"private_doc"});
  }

  assert_not allow(User{"member_user"}, "read", Documents{"private_doc"});
}

test "Members can read public documents" {
  setup {
    has_role(User{"member_user"}, "member", Organization{"org_3"});
    has_relation(Documents{"public_doc"}, "organization", Organization{"org_3"});
  }

  assert allow(User{"member_user"}, "read", Documents{"public_doc"});
}
```