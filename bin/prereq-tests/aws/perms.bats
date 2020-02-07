#!/usr/bin/env bats

USER_ARN=$(aws sts get-caller-identity | jq -r '.Arn')

@test "EKS" {
  ACTION="eks:CreateCluster"

  run aws iam simulate-principal-policy \
      --policy-source-arn "$USER_ARN" \
      --action-names "$ACTION"
  [ "$status" -eq 0 ]

  decision=$(echo "$output" | jq -r '.EvaluationResults[0].EvalDecision')
  [ "$decision" == "allowed" ]

}

@test "RDS" {
  ACTION="rds:CreateDBCluster"

  run aws iam simulate-principal-policy \
      --policy-source-arn "$USER_ARN" \
      --action-names "$ACTION"
  [ "$status" -eq 0 ]

  decision=$(echo "$output" | jq -r '.EvaluationResults[0].EvalDecision')
  [ "$decision" == "allowed" ]

}

@test "Route53" {
  ACTION="route53:ChangeResourceRecordSets"

  run aws iam simulate-principal-policy \
      --policy-source-arn "$USER_ARN" \
      --action-names "$ACTION"
  [ "$status" -eq 0 ]

  decision=$(echo "$output" | jq -r '.EvaluationResults[0].EvalDecision')
  [ "$decision" == "allowed" ]

}




