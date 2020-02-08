#!/usr/bin/env bats

USER_ARN=$(aws sts get-caller-identity | jq -r '.Arn')

check_action () {
  ACTION=$1

  run aws iam simulate-principal-policy \
      --policy-source-arn "$USER_ARN" \
      --action-names "$ACTION"
  if [ "$status" -ne 0 ]; then
    echo "$output"
  fi
  [ "$status" -eq 0 ]

  result=$output
  if [ "$decision" != "allowed" ]; then
    echo "$result"
  fi
  decision=$(echo "$output" | jq -r '.EvaluationResults[0].EvalDecision')
  [ "$decision" == "allowed" ]
}

@test "EKS" {
  check_action "eks:CreateCluster"
}

@test "RDS" {
  check_action "rds:CreateDBCluster"
}

@test "Route53" {
  check_action "route53:ChangeResourceRecordSets"
}




