actor User {}

resource Organization {
  roles = ["admin", "member"];
  permissions = ["read", "write"];
  relations = { documents: Documents };

  "write" if "admin";
  "read" if "member";
  "member" if "admin";
}

resource Documents {
  roles = ["reader", "editor"];
  permissions = ["read", "edit"];
  relations = { creator: User, organization: Organization };

  # RBAC for document roles
  "edit" if "editor";
  "read" if "reader";

  # Organization admin can read and edit all docs in their org
  "read" if "admin" on "organization";
  "edit" if "admin" on "organization";

  # Organization member can read non-private docs in their org
  "read" if "member" on "organization" and not is_private(resource);

  # Inherit all org roles as doc roles
  role if role on "organization";
}

# ABAC helper for is_private field
is_private(doc: Documents) if
  has_is_private(doc, Boolean{true});

is_private(doc: Documents) if
  has_is_private(doc, true);

# TESTS
test "org admin can read and edit all documents" {
  setup {
    has_role(User{"alice"}, "admin", Organization{"org-1"});
    has_relation(Documents{"doc-1"}, "organization", Organization{"org-1"});
    has_is_private(Documents{"doc-1"}, Boolean{true});
    has_relation(Documents{"doc-2"}, "organization", Organization{"org-1"});
    has_is_private(Documents{"doc-2"}, Boolean{false});
    has_relation(Documents{"doc-3"}, "organization", Organization{"org-2"});
    has_is_private(Documents{"doc-3"}, Boolean{false});
  }

  assert allow(User{"alice"}, "read", Documents{"doc-1"});
  assert allow(User{"alice"}, "edit", Documents{"doc-1"});
  assert allow(User{"alice"}, "read", Documents{"doc-2"});
  assert allow(User{"alice"}, "edit", Documents{"doc-2"});
  assert_not allow(User{"alice"}, "read", Documents{"doc-3"});
  assert_not allow(User{"alice"}, "edit", Documents{"doc-3"});
}

test "org member can only read non-private documents" {
  setup {
    has_role(User{"bob"}, "member", Organization{"org-1"});
    has_relation(Documents{"doc-1"}, "organization", Organization{"org-1"});
    has_is_private(Documents{"doc-1"}, Boolean{true});
    has_relation(Documents{"doc-2"}, "organization", Organization{"org-1"});
    has_is_private(Documents{"doc-2"}, Boolean{false});
    has_relation(Documents{"doc-3"}, "organization", Organization{"org-2"});
    has_is_private(Documents{"doc-3"}, Boolean{false});
  }

  assert_not allow(User{"bob"}, "read", Documents{"doc-1"});
  assert allow(User{"bob"}, "read", Documents{"doc-2"});
  assert_not allow(User{"bob"}, "edit", Documents{"doc-2"});
  assert_not allow(User{"bob"}, "read", Documents{"doc-3"});
}
