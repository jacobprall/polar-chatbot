# example reference policy
actor User {
}

resource Tenant {
  roles = ["admin", "member"];
#   "create", "update", and "delete" only applies to resources that roll up to Tenant
#   "read" applies to all
  permissions = [
    "read",
    "create_user",
    "update_user",
    "delete_user",
    "create_environment"
  ];

  # admins can do everyting members can
  "member" if "admin";

  "read" if "member";
  "create_environment" if "member";

  "create_user" if "admin";
  "update_user" if "admin";
  "delete_user" if "admin";
}

resource Environment {
  # note that we do not write these roles, we infer them from the role on the parent
  roles = ["admin", "member"];
#   "create" only applies to resources that roll up to Environment, not Environment
#   "read", "update", and "delete" apply to resources that roll up to Environment including Environment
  permissions = [
    "read",
    "create_token",
    "delete_token",
    "update_policy",
    "create_fact",
    "delete_fact",
    "update_environment",
    "delete_environment"
  ];

  relations = { tenant: Tenant };

  # Environment roles are inherited from the Tenant
  "member" if "member" on "tenant";
  "admin" if "admin" on "tenant";

  "read" if "member";

  "create_token" if "admin";
  "delete_token" if "admin";
  "update_policy" if "admin";
  "create_fact" if "admin";
  "delete_fact" if "admin";
  "update_environment" if "admin";
  "delete_environment" if "admin";
}

# admin vs. member only matters if the Environment is a production env. if it's
# not, then members have the same permissions as admins
has_role(u: User, "admin", env: Environment) if
  has_role(u, "member", env) and
  is_prod(env, false);
