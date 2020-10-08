set search_path to "houston$default";
ALTER TABLE "houston$default"."RoleBinding" RENAME COLUMN "user" TO "userId";
ALTER TABLE "houston$default"."RoleBinding" RENAME COLUMN "serviceAccount" TO "serviceAccountId";
ALTER TABLE "houston$default"."RoleBinding" RENAME COLUMN "workspace" TO "workspaceId";
ALTER TABLE "houston$default"."RoleBinding" RENAME COLUMN "deployment" TO "deploymentId";
ALTER TABLE "houston$default"."Email" RENAME COLUMN "user" TO "userId";
ALTER TABLE "houston$default"."OAuthCredential" RENAME COLUMN "user" TO "userId";
ALTER TABLE "houston$default"."InviteToken" RENAME COLUMN "workspace" TO "workspaceId";
ALTER TABLE "houston$default"."Deployment" RENAME COLUMN "workspace" TO "workspaceId";
ALTER TABLE "houston$default"."Deployment" alter column config type jsonb using config::JSON;
ALTER TABLE "houston$default"."DockerImage" alter column labels type jsonb using labels::JSON;
ALTER TABLE "houston$default"."DockerImage" alter column env type jsonb using env::JSON;
ALTER TABLE "houston$default"."DockerImage" RENAME COLUMN "deployment" TO "deploymentId";
ALTER TABLE "houston$default"."User" RENAME COLUMN "localCredential" TO "localCredentialId";

DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'Role') THEN
    CREATE TYPE "houston$default"."Role" AS ENUM ('SYSTEM_ADMIN', 'SYSTEM_EDITOR', 'SYSTEM_VIEWER', 'WORKSPACE_ADMIN', 'WORKSPACE_EDITOR', 'WORKSPACE_VIEWER', 'DEPLOYMENT_ADMIN', 'DEPLOYMENT_EDITOR', 'DEPLOYMENT_VIEWER', 'USER');
END IF;

IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'InviteSource') THEN
  CREATE TYPE "houston$default"."InviteSource" AS ENUM ('SYSTEM', 'WORKSPACE');
END IF;
END $$;

alter table "houston$default"."InviteToken" ALTER COLUMN source TYPE "houston$default"."InviteSource" using source::"InviteSource";
alter table "houston$default"."InviteToken" ALTER COLUMN role TYPE "houston$default"."Role" using role::"Role";
alter table "houston$default"."RoleBinding" ALTER COLUMN role TYPE "houston$default"."Role" using role::"Role";
CREATE UNIQUE INDEX "RoleBinding_serviceAccountId_unique" ON "RoleBinding"("serviceAccountId");
CREATE UNIQUE INDEX "User_localCredentialId_unique" ON "User"("localCredentialId");

-- migrate varchar(25) => varchar(30)
ALTER TABLE "houston$default"."User" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."User" ALTER COLUMN "localCredentialId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."RoleBinding" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."RoleBinding" ALTER COLUMN "userId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."RoleBinding" ALTER COLUMN "serviceAccountId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."RoleBinding" ALTER COLUMN "workspaceId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."RoleBinding" ALTER COLUMN "deploymentId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."Email" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."Email" ALTER COLUMN "userId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."LocalCredential" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."OAuthCredential" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."OAuthCredential" ALTER COLUMN "userId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."InviteToken" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."InviteToken" ALTER COLUMN "workspaceId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."ServiceAccount" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."Workspace" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."Deployment" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."Deployment" ALTER COLUMN "workspaceId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."DockerImage" ALTER COLUMN "id" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."DockerImage" ALTER COLUMN "deploymentId" SET DATA TYPE varchar(30);
ALTER TABLE "houston$default"."PlatformRelease" ALTER COLUMN "id" SET DATA TYPE varchar(30);

-- migrate Deployment_alertEmails"
ALTER TABLE "houston$default"."Deployment" ADD COLUMN "alertEmails" text[];
UPDATE "houston$default"."Deployment" AS v
SET "alertEmails" = s.alert_emails
FROM (select string_to_array(string_agg(value, ',' order by position),',') as alert_emails, "nodeId" from "houston$default"."Deployment_alertEmails" group by "nodeId") AS s
WHERE v.id = s."nodeId";
DROP table if exists "houston$default"."Deployment_alertEmails";
