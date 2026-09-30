-- pandoc-environments.lua
-- Pandoc Lua filter to convert markdown theorem/definition environments to LaTeX
--
-- This filter processes Div elements with a class name and converts them to
-- LaTeX environments via \begin{} and \end{} blocks. The conversion is 1:1:
-- any class name becomes the LaTeX environment name.
--
-- For LaTeX output only. No validation of environment names--users must ensure
-- the corresponding LaTeX environment is defined in the preamble.

-- A paragraph consisting only of display math ($$ ... $$ set off by blank lines).
local function is_display(block)
  if block.t ~= "Para" then
    return false
  end
  local has_math = false
  for _, el in ipairs(block.content) do
    if el.t == "Math" and el.mathtype == "DisplayMath" then
      has_math = true
    elseif el.t ~= "Space" and el.t ~= "SoftBreak" then
      return false
    end
  end
  return has_math
end

local function append(para, inlines)
  para.content:insert(pandoc.SoftBreak())
  para.content:extend(inlines)
end

-- Join display math with the surrounding paragraphs. Markdown sources set
-- displays off by blank lines, which LaTeX reads as paragraph breaks: the
-- display opens an empty line and the text after it gets a first-line
-- indent. In LaTeX a display belongs to its paragraph.
function Blocks(blocks)
  if FORMAT ~= "latex" then
    return nil
  end
  local out = pandoc.List()
  local i = 1
  while i <= #blocks do
    local block = blocks[i]
    if is_display(block) then
      local prev = out[#out]
      local para
      if prev and prev.t == "Para" then
        append(prev, block.content)
        para = prev
      else
        para = block
        out:insert(para)
      end
      local nxt = blocks[i + 1]
      if nxt and nxt.t == "Para" and not is_display(nxt) then
        append(para, nxt.content)
        i = i + 1
      end
    else
      out:insert(block)
    end
    i = i + 1
  end
  return out
end

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
  local end_cmd = "\\end{" .. env_name .. "}"

  local result = { begin_block }
  for _, block in ipairs(elem.content) do
    table.insert(result, block)
  end

  -- If the environment ends in a paragraph, close it inside that paragraph.
  -- A separate block would be preceded by a blank line (\par), pushing
  -- end marks such as amsthm's \qed onto a line of their own.
  local last = result[#result]
  if #result > 1 and (last.t == "Para" or last.t == "Plain") then
    table.insert(last.content, pandoc.SoftBreak())
    table.insert(last.content, pandoc.RawInline("latex", end_cmd))
  else
    table.insert(result, pandoc.RawBlock("latex", end_cmd))
  end

  return result
end
