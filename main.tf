terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
      bucket = "sentiment-demo-jambread-2026"
      key = "terraform/state.tfstate"
      region = "ap-northeast-2"
  }
}

provider "aws" {
  region = "ap-northeast-2"
}

data "aws_ecr_repository" "existing_ecr" {
  name = "sentiment-lambda" 
}

resource "aws_lambda_function" "sentiment_api" {
  function_name = "sentiment-api"
  
  memory_size   = 2048 
  
  package_type  = "Image"
  image_uri     = "${data.aws_ecr_repository.existing_ecr.repository_url}:latest"
  
  role          = data.aws_lambda_function.existing_lambda_info.role
}

data "aws_lambda_function" "existing_lambda_info" {
  function_name = "sentiment-api"
}

output "lambda_arn" {
  value = data.aws_lambda_function.existing_lambda_info.arn
}