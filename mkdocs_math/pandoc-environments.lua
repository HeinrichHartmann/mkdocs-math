-- pandoc-environments.lua
-- Pandoc Lua filter to convert markdown theorem/definition environments to LaTeX
--
-- This filter processes Div elements with a class name and converts them to
-- LaTeX environments via \begin{} and \end{} blocks. The conversion is 1:1:
-- any class name becomes the LaTeX environment name.
--
-- For LaTeX output only. No validation of environment names--users must ensure
-- the corresponding LaTeX environment is defined in the preamble.

function Div(elem)
  -- Only process if converting to LaTeX
  if FORMAT ~= "latex" then
    return elem
  end

  -- Get the first class as the environment name
  local env_name = elem.classes[1]
  if not env_name then
    return elem
  end

  -- Extract optional label from data-label attribute
  local label = elem.attributes["data-label"]

  -- Build the \begin{} command with optional label if present
  local begin_cmd = "\\begin{" .. env_name .. "}"
  if label then
    -- For proof environments, prepend "Proof " to the label
    -- since amsthm replaces the entire proof text with the optional argument
    if env_name == "proof" then
      begin_cmd = "\\begin{" .. env_name .. "}[Proof " .. label .. "]"
    else
      begin_cmd = "\\begin{" .. env_name .. "}[" .. label .. "]"
    end
  end

  -- Convert the div content to LaTeX by wrapping with \begin{} and \end{}
  local begin_block = pandoc.RawBlock("latex", begin_cmd)
  local end_block = pandoc.RawBlock("latex", "\\end{" .. env_name .. "}")

  -- Return a sequence: begin block, content blocks, end block
  local result = { begin_block }
  for _, block in ipairs(elem.content) do
    table.insert(result, block)
  end
  table.insert(result, end_block)

  return result
end
