
# Cost-Aware Adaptive Verification for Long-Horizon LLM Agents

## Overview

This project investigates whether a long-horizon, tool-using LLM agent can dynamically decide when to verify its own actions.

The goal is to maintain reliability close to verifying every action while reducing unnecessary verification calls, latency, and token cost.

## Research Question

Can an LLM agent selectively verify risky actions using cheap and explainable risk signals instead of verifying every action?

## Core System

The project uses a controlled synthetic environment where an LLM agent performs multi-step tasks.

The main pipeline is:

Task
→ LLM Agent
→ Tool Call
→ Fault Injection
→ Verification Policy
→ Self-Verifier (when triggered)
→ Recovery
→ Next Action
→ Oracle Evaluation
→ Logging

## Verification Policies

- Policy A: No Verification
- Policy B: Verify Every Step
- Policy C: Fixed Verification Schedule
- Policy D: Risk-Triggered Adaptive Verification

## Experimental Environment

The initial environment is a synthetic e-commerce/order-management environment containing tools such as:

- search_product
- get_price
- check_stock
- update_cart
- apply_discount
- process_payment
- update_address
- cancel_order

## Evaluation

The project evaluates:

- Task Success
- Failure Recovery
- Error Propagation
- Verification Overhead
- Token Cost
- Latency
- Reliability vs Verification Budget

## Project Status

Initial repository setup.

Implementation will proceed through:

1. Deterministic environment
2. Task dataset and oracle
3. Fault injector
4. LLM agent
5. Self-verifier and recovery
6. Verification policies
7. Experiment harness
8. Evaluation and analysis
